import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import create_batch
from frappe.utils.data import add_days, cint, cstr, flt, get_datetime, now_datetime

from commera.api.cart import validate_stock_available
from commera.discounts.allocations import get_allocations, get_price_discount_rows
from commera.discounts.cart_context import get_cart_context
from commera.discounts.codes import get_code_discount, normalize_code
from commera.discounts.doctype.commera_discount.commera_discount import SHIPPING, DiscountCodeError
from commera.discounts.preview import get_preview_quotation
from commera.discounts.pricing import get_saving, select_discounts
from commera.discounts.selection import (
	Selection,
	get_discount,
	get_discount_codes,
	get_unmet_reason,
	get_unusable_code_reason,
	validate_new_discount_code,
)
from commera.guest import clear_guest_cart_cookie, get_guest_cart_key, is_guest, set_guest_cart_cookie
from commera.plugin_events import fire_event, get_handlers
from commera.utils import get_available_stocks, get_free_delivery

MAX_CART_LINES = 50
# Discount pricing slows down with every unit, so even an item that never runs out has a limit.
MAX_LINE_QUANTITY = 100
ABANDONED_GUEST_CART_DAYS = 30


def get_max_line_quantity() -> int:
	return cint(frappe.get_cached_doc("Commera Settings").max_cart_line_quantity) or MAX_LINE_QUANTITY


class CommeraCart(Document):
	def validate(self):
		if len(self.lines) > MAX_CART_LINES:
			frappe.throw(_("A cart holds at most {0} lines.").format(MAX_CART_LINES))
		max_line_quantity = get_max_line_quantity()
		for line in self.lines:
			if cint(line.qty) < 1:
				frappe.throw(_("Row {0}: the quantity must be at least 1.").format(line.idx))
			if cint(line.qty) > max_line_quantity:
				frappe.throw(
					_("Row {0}: a cart line holds at most {1} units.").format(line.idx, max_line_quantity)
				)
			attributes = parse_attributes(line.attributes)
			line.attributes = frappe.as_json(attributes, indent=None) if attributes else None
		self.validate_stock()

	def validate_stock(self):
		# Only what grew: a line stock fell under since it was added must not block every other cart edit.
		previous = self.get_doc_before_save()
		previous_quantities = get_quantities_by_item_code(previous.lines) if previous else {}
		grown = {
			item_code: qty
			for item_code, qty in get_quantities_by_item_code(self.lines).items()
			if qty > previous_quantities.get(item_code, 0)
		}
		if grown:
			validate_stock_available(
				[{"variant": {"item_code": item_code}, "qty": qty} for item_code, qty in grown.items()]
			)

	def cap_at_stock(self):
		quantities = get_quantities_by_item_code(self.lines)
		warehouse = frappe.get_cached_value("Commera Settings", "Commera Settings", "ecommerce_warehouse")
		stock_by_item_code = get_available_stocks(list(quantities), warehouse)
		for item_code, qty in quantities.items():
			stock = stock_by_item_code.get(item_code, {})
			available = max(cint(stock.get("stock_qty")), 0)
			if not stock.get("unlimited") and qty > available:
				rows = [row for row in self.lines if row.item_code == item_code]
				change_quantity_from_the_end(self, rows, available - qty)

	def after_insert(self):
		# Most guest carts never reach checkout, so the event is only logged when an app listens for it.
		if get_handlers("commera_events", "cart_created"):
			fire_event("cart_created", self.doctype, self.name, data={"user": self.user})

	@property
	def version(self) -> str:
		return str(get_datetime(self.modified))

	def add_lines(self, lines: list[dict]):
		for line in lines:
			attributes = parse_attributes(line.get("attributes"))
			qty = cint(line.get("qty") or 1)
			selected = cint(line.get("selected", 1))
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
				existing_line.selected = cint(existing_line.selected) or selected
			else:
				self.append(
					"lines",
					{
						"item_code": line["item_code"],
						"qty": qty,
						"attributes": attributes,
						"selected": selected,
					},
				)

	def update_lines(self, lines: list[dict]):
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

	def set_selection(self, selection: dict[str, bool]) -> bool:
		changed = False
		for row in self.lines:
			selected = cint(selection.get(row.item_code, 1))
			changed = changed or cint(row.selected) != selected
			# Set even when unchanged: a new line's None would take the field's default of 1 on insert.
			row.selected = selected
		return changed

	def get_selected_lines(self) -> list:
		return [row for row in self.lines if cint(row.selected)]

	def add_discount_code(self, code: str):
		codes = [applied_code for applied_code in get_discount_codes(self) if get_code_discount(applied_code)]
		preview = self.get_quotation_preview()
		# A code that does not combine still joins the cart: pricing keeps whichever saves the shopper more.
		code = validate_new_discount_code(code, codes, active_codes=[])
		if refusal := get_unusable_code_reason(preview, code):
			frappe.throw(refusal, DiscountCodeError)
		self.discount_codes = "\n".join([*codes, code])

	def remove_discount_code(self, code: str):
		code = normalize_code(code)
		self.discount_codes = "\n".join(name for name in get_discount_codes(self) if name != code)

	def get_lines_by_item_code(self) -> dict[str, list]:
		lines_by_item_code = {}
		for row in self.get_selected_lines():
			lines_by_item_code.setdefault(row.item_code, []).append(row)
		return lines_by_item_code

	def get_priced_cart(self) -> dict:
		# Unticked lines are priced on their own, without discounts.
		quotation = self.get_quotation_preview()
		selected_lines = self.get_selected_lines()
		items_by_row = dict(zip([row.name for row in selected_lines], quotation.items, strict=True))
		if other_lines := [row for row in self.lines if not cint(row.selected)]:
			plain_quotation = get_preview_quotation(
				get_preview_lines(other_lines), user=self.user, flags={"commera_discounts": []}
			)
			items_by_row.update(zip([row.name for row in other_lines], plain_quotation.items, strict=True))
		return {
			"name": self.name,
			"version": self.version,
			"attributes": parse_attributes(self.attributes),
			"currency": quotation.currency,
			"discount_codes": get_code_states(quotation),
			"automatic_discounts": get_automatic_discounts(quotation),
			"discounts": get_price_discount_rows(quotation),
			"lines": [get_priced_line(row, items_by_row[row.name]) for row in self.lines],
			"subtotal": flt(quotation.total),
			"order_discount": flt(quotation.custom_code_order_discount),
			"total": flt(quotation.net_total),
			**get_free_delivery(quotation),
		}

	def get_quotation_preview(self):
		fields = {**frappe.parse_json(self.plugin_fields or "{}"), "custom_cart_attributes": self.attributes}
		return get_preview_quotation(
			get_preview_lines(self.get_selected_lines()), self.discount_codes, self.user, fields=fields
		)

	def update_quotation(self, quotation):
		# Split by attributes only while the qty still matches the ticked lines.
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


def get_preview_lines(rows: list) -> list[dict]:
	return [{"item_code": row.item_code, "qty": row.qty} for row in rows]


def get_quantities_by_item_code(rows: list) -> dict[str, int]:
	quantities = {}
	for row in rows:
		quantities[row.item_code] = quantities.get(row.item_code, 0) + cint(row.qty)
	return quantities


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
		label = blocking.code or blocking.discount.title
		own = [Selection(discount, code), *(s for s in selections if discount.can_combine_with(s.discount))]
		if flt(get_saving(cart, own), 2) < flt(get_saving(cart, selections), 2):
			return _("{0} doesn't combine with {1}, which saves you more.").format(discount.title, label)
		return _("{0} doesn't combine with {1}.").format(discount.title, label)
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
		"selected": bool(cint(row.selected)),
		"attributes": parse_attributes(row.attributes),
		"price": flt(item.price_list_rate),
		"rate": flt(item.rate),
		"code_discount": flt(item.custom_code_discount),
		"discount": item.custom_discount,
		"amount": flt(item.amount),
	}


def parse_attributes(attributes) -> dict:
	attributes = frappe.parse_json(attributes) if attributes else {}
	if not isinstance(attributes, dict):
		frappe.throw(_("Line attributes must be a JSON object."))
	return {cstr(key): cstr(value) for key, value in attributes.items()}


def get_session_cart(create: bool = False) -> CommeraCart | None:
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
	# modified is left alone so the next browser sync is not a version conflict.
	cart = frappe.qb.DocType("Commera Cart")
	if quotation.custom_guest_cart_key:
		condition = cart.cart_key == quotation.custom_guest_cart_key
	elif shopper:
		condition = cart.user == shopper
	else:
		return
	cart_name = frappe.qb.from_(cart).select(cart.name).where(condition).run(pluck=True)
	if not cart_name:
		return
	frappe.qb.update(cart).set(cart.discount_codes, None).set(cart.attributes, None).where(
		cart.name == cart_name[0]
	).run()
	# The webhook can place the order while the shopper never comes back to sync the browser cart.
	line = frappe.qb.DocType("Commera Cart Line")
	frappe.qb.from_(line).delete().where(
		(line.parent == cart_name[0]) & (line.parenttype == "Commera Cart") & (line.selected == 1)
	).run()


def delete_abandoned_guest_carts():
	cutoff = add_days(now_datetime(), -ABANDONED_GUEST_CART_DAYS)
	names = frappe.get_all(
		"Commera Cart", filters={"user": ["is", "not set"], "modified": ["<", cutoff]}, pluck="name"
	)
	for batch in create_batch(names, 500):
		frappe.db.delete("Commera Cart Line", {"parent": ["in", batch], "parenttype": "Commera Cart"})
		frappe.db.delete("Commera Cart", {"name": ["in", batch]})
		frappe.db.commit()  # nosemgrep: frappe-manual-commit  # a daily job; each batch stands alone


def keep_guest_cart(login_manager=None):
	adopt_guest_cart(get_guest_cart_key())


def set_guest_cart_key(cart_key: str, new_cart_key: str):
	frappe.db.set_value(
		"Commera Cart", {"cart_key": cart_key}, "cart_key", new_cart_key, update_modified=False
	)
	frappe.db.set_value(
		"Quotation",
		{"custom_guest_cart_key": cart_key, "order_type": "Shopping Cart", "docstatus": 0},
		"custom_guest_cart_key",
		new_cart_key,
		update_modified=False,
	)


def adopt_guest_cart(cart_key: str | None):
	"""Move a guest cart into the signed-in shopper's cart. A failed merge is logged, never raised."""
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
			{
				"item_code": row.item_code,
				"qty": row.qty,
				"attributes": parse_attributes(row.attributes),
				"selected": row.selected,
			}
			for row in guest_cart.lines
		]
	)
	account_cart.cap_at_stock()
	account_cart.set_attributes(parse_attributes(guest_cart.attributes))
	for code in get_discount_codes(guest_cart):
		try:
			account_cart.add_discount_code(code)
		except frappe.ValidationError:
			# A code the account cart refuses, such as one already used, is left behind.
			frappe.clear_last_message()
	account_cart.save(ignore_permissions=True)
	frappe.delete_doc("Commera Cart", guest_cart.name, ignore_permissions=True, force=True)
