import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.data import cint, cstr, flt, get_datetime

from commera.commera_ecommerce.doctype.commera_discount.commera_discount import get_code_name
from commera.discount_codes import (
	apply_code_discounts,
	get_discount,
	get_discount_codes,
	validate_new_discount_code,
)
from commera.guest import get_guest_cart_key, is_guest, set_guest_cart_cookie

MAX_CART_LINES = 50


class CommeraCart(Document):
	"""The shopper's cart on the server: lines with attributes, and discount codes. ERPNext prices it."""

	def validate(self):
		if len(self.lines) > MAX_CART_LINES:
			frappe.throw(_("A cart holds at most {0} lines.").format(MAX_CART_LINES))
		for line in self.lines:
			if cint(line.qty) < 1:
				frappe.throw(_("Row {0}: the quantity must be at least 1.").format(line.idx))
			attributes = parse_attributes(line.attributes)
			line.attributes = frappe.as_json(attributes, indent=None) if attributes else None

	@property
	def version(self) -> str:
		return str(get_datetime(self.modified))

	def add_lines(self, lines: list[dict]):
		"""Add lines; a line with the same item and attributes as an existing one adds to its quantity."""
		for line in lines:
			attributes = parse_attributes(line.get("attributes"))
			qty = cint(line.get("qty") or 1)
			existing_line = next(
				(
					row
					for row in self.lines
					if row.item_code == line["item_code"] and parse_attributes(row.attributes) == attributes
				),
				None,
			)
			if existing_line:
				existing_line.qty = cint(existing_line.qty) + qty
			else:
				self.append("lines", {"item_code": line["item_code"], "qty": qty, "attributes": attributes})

	def update_lines(self, lines: list[dict]):
		"""Set the quantity or attributes of lines by `line_id`. A quantity of 0 removes the line."""
		for line in lines:
			row = self.get_line(line["line_id"])
			if "attributes" in line:
				row.attributes = parse_attributes(line["attributes"])
			if "qty" in line:
				row.qty = cint(line["qty"])
		self.lines = [row for row in self.lines if cint(row.qty) > 0]

	def remove_lines(self, line_ids: list[str]):
		for line_id in line_ids:
			self.get_line(line_id)
		self.lines = [row for row in self.lines if row.name not in line_ids]

	def get_line(self, line_id: str):
		row = next((row for row in self.lines if row.name == line_id), None)
		if not row:
			frappe.throw(_("Cart line {0} was not found.").format(line_id), frappe.DoesNotExistError)
		return row

	def set_quantities(self, quantities: dict[str, int]) -> bool:
		"""Match the browser cart's quantity per item, keeping each line's attributes. Return True on a change."""
		changed = False
		for item_code in {row.item_code for row in self.lines} - set(quantities):
			self.lines = [row for row in self.lines if row.item_code != item_code]
			changed = True

		for item_code, qty in quantities.items():
			rows = [row for row in self.lines if row.item_code == item_code]
			delta = cint(qty) - sum(cint(row.qty) for row in rows)
			if not delta:
				continue
			changed = True
			if not rows:
				self.append("lines", {"item_code": item_code, "qty": cint(qty)})
				continue
			change_quantity_from_the_end(self, rows, delta)
		return changed

	def add_discount_code(self, code: str):
		codes = get_discount_codes(self)
		codes.append(validate_new_discount_code(code, codes))
		self.discount_codes = "\n".join(codes)

	def remove_discount_code(self, code: str):
		code = get_code_name(code)
		self.discount_codes = "\n".join(name for name in get_discount_codes(self) if name != code)

	def get_lines_by_item_code(self) -> dict[str, list]:
		lines_by_item_code = {}
		for row in self.lines:
			lines_by_item_code.setdefault(row.item_code, []).append(row)
		return lines_by_item_code

	def get_priced_cart(self) -> dict:
		"""The cart priced as checkout would price it: ERPNext price lists and rules, then the codes."""
		quotation = self.get_quotation_preview()
		lines_by_row = dict(zip([row.name for row in self.lines], quotation.items, strict=True))
		return {
			"name": self.name,
			"version": self.version,
			"currency": quotation.currency,
			"discount_codes": [
				{"code": code, "class": get_discount(code).discount_class}
				for code in get_discount_codes(self)
			],
			"lines": [get_priced_line(row, lines_by_row[row.name]) for row in self.lines],
			"subtotal": flt(quotation.total),
			"order_discount": flt(quotation.custom_code_order_discount),
			"total": flt(quotation.net_total),
		}

	def get_quotation_preview(self):
		"""An unsaved Quotation. Priced elevated, like the checkout cart: ERPNext reads Items the shopper cannot."""
		from commera.api.payments import system_user_session

		settings = frappe.get_cached_doc("Commera Settings")
		quotation = frappe.new_doc("Quotation")
		quotation.update(
			{
				"quotation_to": "Customer",
				"company": settings.get("company") or frappe.defaults.get_global_default("company"),
				"order_type": "Shopping Cart",
				"selling_price_list": settings.sale_price_list,
				"custom_discount_codes": self.discount_codes,
			}
		)
		for row in self.lines:
			quotation.append(
				"items",
				{"item_code": row.item_code, "qty": row.qty, "warehouse": settings.ecommerce_warehouse},
			)
		with system_user_session():
			quotation.run_method("set_missing_values")
			quotation.calculate_taxes_and_totals()
			apply_code_discounts(quotation)
		return quotation

	def update_quotation(self, quotation):
		"""Copy the attributes and codes onto a checkout Quotation whose lines came from the browser. When
		the browser's quantity matches, an item held on several lines stays split by attributes."""
		lines_by_item_code = self.get_lines_by_item_code()
		items = []
		for item in quotation.items:
			lines = lines_by_item_code.get(item.item_code, [])
			row = {"item_code": item.item_code, "warehouse": item.warehouse}
			if len(lines) > 1 and sum(cint(line.qty) for line in lines) == cint(item.qty):
				items.extend(
					{**row, "qty": line.qty, "custom_line_attributes": line.attributes} for line in lines
				)
			else:
				items.append(
					{**row, "qty": item.qty, "custom_line_attributes": lines[0].attributes if lines else None}
				)
		quotation.set("items", items)
		quotation.custom_discount_codes = self.discount_codes


def change_quantity_from_the_end(cart, rows: list, delta: int):
	if delta > 0:
		rows[-1].qty = cint(rows[-1].qty) + delta
		return
	for row in reversed(rows):
		taken = min(cint(row.qty), -delta)
		row.qty = cint(row.qty) - taken
		delta += taken
	cart.lines = [row for row in cart.lines if cint(row.qty) > 0]


def get_priced_line(row, item) -> dict:
	return {
		"line_id": row.name,
		"item_code": row.item_code,
		"title": item.item_name,
		"qty": cint(row.qty),
		"attributes": parse_attributes(row.attributes),
		"price": flt(item.price_list_rate),
		"rate": flt(item.rate),
		"code_discount": flt(item.custom_code_discount),
		"discount_code": item.custom_discount_code,
		"amount": flt(item.amount),
	}


def parse_attributes(attributes) -> dict:
	attributes = frappe.parse_json(attributes) if attributes else {}
	if not isinstance(attributes, dict):
		frappe.throw(_("Line attributes must be a JSON object."))
	return {cstr(key): cstr(value) for key, value in attributes.items()}


def get_session_cart(create: bool = False) -> CommeraCart | None:
	"""The session shopper's cart, locked for this request. With `create`, start one when they have none."""
	filters = {"user": frappe.session.user} if not is_guest() else {"cart_key": get_guest_cart_key()}
	if is_guest() and not filters["cart_key"]:
		filters = None
	name = frappe.db.get_value("Commera Cart", filters, "name", order_by="modified desc") if filters else None
	if name:
		return frappe.get_doc("Commera Cart", name, for_update=True)
	if not create:
		return None

	cart = frappe.new_doc("Commera Cart")
	if is_guest():
		cart.cart_key = set_guest_cart_cookie()
	else:
		cart.user = frappe.session.user
	return cart
