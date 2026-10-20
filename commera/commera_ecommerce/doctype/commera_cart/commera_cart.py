import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.data import cint, cstr, flt, get_datetime

from commera.commera_ecommerce.doctype.commera_discount.commera_discount import SHIPPING, DiscountCodeError
from commera.discounts.allocations import get_allocations, get_price_discount_rows
from commera.discounts.cart_context import get_cart_context
from commera.discounts.codes import get_code_discount, normalize_code
from commera.discounts.preview import get_preview_quotation
from commera.discounts.selection import (
	get_discount,
	get_discount_codes,
	get_unmet_reason,
	get_unusable_code_reason,
	select_discounts,
	validate_new_discount_code,
)
from commera.guest import clear_guest_cart_cookie, get_guest_cart_key, is_guest, set_guest_cart_cookie
from commera.plugin_events import fire_event, get_handlers

MAX_CART_LINES = 50
# Discount pricing slows down with every unit, so even an item that never runs out has a limit.
MAX_LINE_QUANTITY = 100


class CommeraCart(Document):
	"""The shopper's cart on the server: lines with attributes, and discount codes. ERPNext prices it."""

	def validate(self):
		if len(self.lines) > MAX_CART_LINES:
			frappe.throw(_("A cart holds at most {0} lines.").format(MAX_CART_LINES))
		for line in self.lines:
			if cint(line.qty) < 1:
				frappe.throw(_("Row {0}: the quantity must be at least 1.").format(line.idx))
			if cint(line.qty) > MAX_LINE_QUANTITY:
				frappe.throw(
					_("Row {0}: a cart line holds at most {1} units.").format(line.idx, MAX_LINE_QUANTITY)
				)
			attributes = parse_attributes(line.attributes)
			line.attributes = frappe.as_json(attributes, indent=None) if attributes else None

	def after_insert(self):
		# Most guest carts never reach checkout, so the event is only logged when an app listens for it.
		if get_handlers("commera_events", "cart_created"):
			fire_event("cart_created", self.doctype, self.name, data={"user": self.user})

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
		codes = [applied_code for applied_code in get_discount_codes(self) if get_code_discount(applied_code)]
		preview = self.get_quotation_preview()
		active_codes = [selection.code for selection in select_discounts(get_cart_context(preview))]
		code = validate_new_discount_code(code, codes, active_codes)
		if refusal := get_unusable_code_reason(preview, code):
			frappe.throw(refusal, DiscountCodeError)
		self.discount_codes = "\n".join([*codes, code])

	def remove_discount_code(self, code: str):
		code = normalize_code(code)
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
			"attributes": parse_attributes(self.attributes),
			"currency": quotation.currency,
			"discount_codes": get_code_states(quotation),
			"automatic_discounts": get_automatic_discounts(quotation),
			"discounts": get_price_discount_rows(quotation),
			"lines": [get_priced_line(row, lines_by_row[row.name]) for row in self.lines],
			"subtotal": flt(quotation.total),
			"order_discount": flt(quotation.custom_code_order_discount),
			"total": flt(quotation.net_total),
		}

	def get_quotation_preview(self):
		lines = [{"item_code": row.item_code, "qty": row.qty} for row in self.lines]
		fields = {**frappe.parse_json(self.plugin_fields or "{}"), "custom_cart_attributes": self.attributes}
		return get_preview_quotation(lines, self.discount_codes, self.user, fields=fields)

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
		quotation.custom_cart_attributes = self.attributes
		quotation.update(frappe.parse_json(self.plugin_fields or "{}"))

	def set_attributes(self, values: dict):
		"""Merge cart-level attributes; a value of None removes its key."""
		attributes = {
			**parse_attributes(self.attributes),
			**{cstr(key): value for key, value in values.items()},
		}
		attributes = {key: cstr(value) for key, value in attributes.items() if value is not None}
		self.attributes = frappe.as_json(attributes, indent=None) if attributes else None

	def set_plugin_fields(self, values: dict):
		self.plugin_fields = frappe.as_json(
			{**frappe.parse_json(self.plugin_fields or "{}"), **values}, indent=None
		)


def change_quantity_from_the_end(cart, rows: list, delta: int):
	if delta > 0:
		rows[-1].qty = cint(rows[-1].qty) + delta
		return
	for row in reversed(rows):
		taken = min(cint(row.qty), -delta)
		row.qty = cint(row.qty) - taken
		delta += taken
	cart.lines = [row for row in cart.lines if cint(row.qty) > 0]


def get_code_states(quotation) -> list[dict]:
	"""Each code with whether it applies now and, when not, why in the shopper's words."""
	applied = {(row["discount"], row.get("code")) for row in get_allocations(quotation)}
	cart = get_cart_context(quotation)
	selections = select_discounts(cart)
	states = []
	for code in get_discount_codes(quotation):
		discount_name = get_code_discount(code)
		discount = get_discount(discount_name) if discount_name else None
		is_applied = (discount_name, code) in applied
		states.append(
			{
				"code": code,
				"title": discount.title if discount else code,
				"discount_class": discount.discount_class if discount else None,
				"applied": is_applied,
				"reason": None if is_applied else get_code_reason(cart, code, selections),
			}
		)
	return states


def get_code_reason(cart, code: str, selections: list) -> str:
	if reason := get_unusable_code_reason(cart.doc, code):
		return reason
	discount = get_discount(get_code_discount(code))
	if reason := get_unmet_reason(discount, cart):
		return reason
	if not discount.gives_anything(cart):
		if discount.discount_class == SHIPPING:
			return _("{0} does not cover the delivery option you chose.").format(discount.title)
		return _("Nothing in your cart qualifies for {0}.").format(discount.title)
	if discount.discount_class == SHIPPING and any(selection.code == code for selection in selections):
		return _("{0} comes off the delivery charge once you choose a delivery option.").format(
			discount.title
		)
	blocking = next((other for other in selections if not discount.can_combine_with(other.discount)), None)
	if blocking:
		return _("{0} cannot be combined with {1}.").format(
			discount.title, blocking.code or blocking.discount.title
		)
	return _("{0} cannot be combined with your other discounts.").format(discount.title)


def get_automatic_discounts(quotation) -> list[dict]:
	return [
		{"title": row["title"], "amount": row["amount"]}
		for row in get_allocations(quotation)
		if not row.get("code")
	]


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
		"discount": item.custom_discount_code,
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


def clear_ordered_cart(quotation, shopper: str | None):
	"""Codes and attributes belong to the order just placed; left on the cart, the next order would get them.
	`modified` stays, so the browser's next sync is not a version conflict."""
	cart = frappe.qb.DocType("Commera Cart")
	if quotation.custom_guest_cart_key:
		condition = cart.cart_key == quotation.custom_guest_cart_key
	elif shopper:
		condition = cart.user == shopper
	else:
		return
	frappe.qb.update(cart).set(cart.discount_codes, None).set(cart.attributes, None).where(condition).run()


def keep_guest_cart(login_manager=None):
	"""On sign-in, the cart built as a guest becomes the account's cart, or joins it when the account has one.
	A cart that cannot be merged is logged, never a reason to refuse the sign-in."""
	cart_key = get_guest_cart_key()
	guest_cart_name = cart_key and frappe.db.get_value("Commera Cart", {"cart_key": cart_key}, "name")
	if not guest_cart_name or is_guest():
		return
	frappe.db.savepoint("keep_guest_cart")
	try:
		guest_cart = frappe.get_doc("Commera Cart", guest_cart_name, for_update=True)
		account_cart = get_session_cart()
		if account_cart:
			merge_carts(guest_cart, account_cart)
		else:
			guest_cart.update({"user": frappe.session.user, "cart_key": None})
			guest_cart.save(ignore_permissions=True)
	except Exception:
		frappe.db.rollback(save_point="keep_guest_cart")
		frappe.log_error(title=f"Could not keep the guest cart {guest_cart_name} on sign-in")
	clear_guest_cart_cookie()


def merge_carts(guest_cart: CommeraCart, account_cart: CommeraCart):
	account_cart.add_lines(
		[
			{"item_code": row.item_code, "qty": row.qty, "attributes": parse_attributes(row.attributes)}
			for row in guest_cart.lines
		]
	)
	account_cart.set_attributes(parse_attributes(guest_cart.attributes))
	for code in get_discount_codes(guest_cart):
		try:
			account_cart.add_discount_code(code)
		except frappe.ValidationError:
			# A code the account cart refuses, such as one that does not combine with its own, is left behind.
			frappe.clear_last_message()
	account_cart.save(ignore_permissions=True)
	frappe.delete_doc("Commera Cart", guest_cart.name, ignore_permissions=True, force=True)
