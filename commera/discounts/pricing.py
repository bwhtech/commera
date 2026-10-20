import frappe
from frappe.utils.data import flt

from commera.commera_ecommerce.doctype.commera_discount.commera_discount import ORDER, PRODUCT, SHIPPING
from commera.discounts.allocations import ALLOCATIONS_FIELD, get_allocation, get_allocations, set_allocations
from commera.discounts.cart_context import get_cart_context
from commera.discounts.codes import get_code_discount
from commera.discounts.selection import Selection, get_discount, get_discount_codes, select_discounts


def is_storefront_cart(doc) -> bool:
	return doc.doctype == "Quotation" and doc.order_type == "Shopping Cart"


def is_repriced(doc) -> bool:
	"""Only a cart being shopped picks and prices discounts; once submitted, its amounts are the order's."""
	return doc.flags.commera_discounts is not None or (is_storefront_cart(doc) and doc.docstatus == 0)


def remove_code_discounts(doc, method=None):
	"""Take the code discounts off before ERPNext prices the document again, so they never apply twice.
	Clamped at zero: other code may already have reset these fields."""
	if doc.get("is_return") or (doc.doctype == "Quotation" and not is_repriced(doc)):
		return
	keep_lines = not is_repriced(doc)
	for item in doc.items:
		if flt(item.get("custom_code_discount")):
			item.discount_amount = max(flt(item.discount_amount) - flt(item.custom_code_discount), 0)
			item.rate = (flt(item.rate_with_margin) or flt(item.price_list_rate)) - item.discount_amount
		if not keep_lines:
			item.custom_code_discount = 0
			item.custom_discount_code = None

	if flt(doc.get("custom_code_order_discount")):
		doc.discount_amount = max(flt(doc.discount_amount) - flt(doc.custom_code_order_discount), 0)
	doc.custom_code_order_discount = 0


def apply_code_discounts(doc, method=None):
	"""Product discounts per line (best wins), then order discounts on the discounted subtotal. A cart
	chooses and prices its discounts on every save; an order or invoice keeps the amounts its cart had."""
	if not is_repriced(doc):
		if doc.doctype != "Quotation":
			apply_recorded_discounts(doc)
		return
	selections = select_discounts(get_cart_context(doc))
	app_discounts = get_app_discounts(doc)
	allocations = apply_line_discounts(
		doc,
		[s for s in selections if s.discount.discount_class == PRODUCT],
		[d for d in app_discounts if d["discount_class"] == PRODUCT],
	)
	doc.calculate_taxes_and_totals()
	allocations += apply_order_discount(
		doc,
		[s for s in selections if s.discount.discount_class == ORDER],
		[d for d in app_discounts if d["discount_class"] == ORDER],
	)
	doc.calculate_taxes_and_totals()
	allocations += get_shipping_allocations(doc)
	set_allocations(doc, allocations)


def get_app_discounts(doc) -> list[dict]:
	"""A cart asks the apps; a merchant's test cart does not."""
	if doc.flags.commera_discounts is not None:
		return []
	# Imported here: commera.checkout_hooks imports the shipping step, which reaches this package.
	from commera.checkout_hooks import get_plugin_discounts

	return get_plugin_discounts(doc)


def apply_line_discounts(doc, selections: list, app_discounts: list[dict]) -> list[dict]:
	"""Each line takes its single best offer: a merchant's product discount or an app's line discount."""
	cart = get_cart_context(doc)
	best_by_line = {}

	def offer(idx: int, amount: float, allocation: dict):
		if amount > best_by_line.get(idx, (0, None))[0]:
			best_by_line[idx] = (amount, allocation)

	for selection in selections:
		line_discounts = cap_by_budget(selection.discount, selection.discount.get_line_discounts(cart))
		for idx, amount in line_discounts.items():
			offer(idx, amount, get_allocation(selection, PRODUCT, 0, idx))
	for app_discount in app_discounts:
		offer(app_discount["line"], app_discount["amount"], dict(app_discount))

	allocations = []
	for item in doc.items:
		if item.idx not in best_by_line:
			continue
		amount, allocation = best_by_line[item.idx]
		unit_discount = flt(min(amount / flt(item.qty), flt(item.rate)), item.precision("discount_amount"))
		add_line_discount(item, unit_discount)
		item.custom_discount_code = allocation["discount"]
		allocations.append({**allocation, "amount": flt(unit_discount * flt(item.qty), 2)})
	return allocations


def add_line_discount(item, unit_discount: float):
	# ERPNext rebuilds a percentage discount from the price list, which would drop this share.
	item.discount_percentage = 0
	item.discount_amount = flt(item.discount_amount) + unit_discount
	item.rate = flt(item.rate) - unit_discount
	item.custom_code_discount = unit_discount


def apply_order_discount(doc, selections: list, app_discounts: list[dict]) -> list[dict]:
	cart = get_cart_context(doc)
	offers = []
	for selection in selections:
		amount = flt(selection.discount.get_order_discount(cart))
		budget_left = selection.discount.budget_left
		offers.append(
			(
				min(amount, budget_left) if budget_left is not None else amount,
				get_allocation(selection, ORDER, 0),
			)
		)
	offers += [(app_discount["amount"], dict(app_discount)) for app_discount in app_discounts]

	allocations = []
	subtotal = flt(doc.total)
	for amount, allocation in offers:
		amount = flt(
			min(amount, subtotal - sum(row["amount"] for row in allocations)),
			doc.precision("discount_amount"),
		)
		if amount > 0:
			allocations.append({**allocation, "amount": amount})

	total = sum(row["amount"] for row in allocations)
	if total:
		# Like Shopify, an order discount comes off the subtotal, before tax and shipping.
		if not flt(doc.discount_amount):
			doc.apply_discount_on = "Net Total"
		# ERPNext's own percentage discount is kept as an amount, so this share can be added to it.
		doc.discount_amount = flt(doc.discount_amount) + total
		doc.additional_discount_percentage = 0
		doc.custom_code_order_discount = total
	return allocations


def apply_recorded_discounts(doc):
	"""Give an order, invoice or credit note the discounts its cart was priced with: the same amount off
	each unit, and its share of each order discount by subtotal."""
	recorded = get_allocations(doc)
	if not recorded:
		return

	allocations = []
	for item in doc.items:
		if not flt(item.get("custom_code_discount")):
			continue
		if not doc.get("is_return"):
			add_line_discount(item, flt(item.custom_code_discount))
		row = next(
			(
				row
				for row in recorded
				if row["discount_class"] == PRODUCT and row.get("discount") == item.custom_discount_code
			),
			None,
		)
		if row:
			amount = flt(flt(item.custom_code_discount) * flt(item.qty), 2)
			allocations.append({**row, "amount": amount, "line": item.idx})
	doc.calculate_taxes_and_totals()

	order_rows = [row for row in recorded if row["discount_class"] == ORDER]
	source = get_discount_source(doc) if order_rows else None
	shares = get_order_discount_shares(doc, order_rows, source)
	if order_rows:
		doc.discount_amount = get_other_order_discount(doc, source) + sum(shares)
		doc.additional_discount_percentage = 0
		doc.custom_code_order_discount = sum(shares)
		doc.calculate_taxes_and_totals()
	allocations += [{**row, "amount": share} for row, share in zip(order_rows, shares, strict=True)]
	allocations += [row for row in recorded if row["discount_class"] == SHIPPING]
	set_allocations(doc, allocations)


def get_other_order_discount(doc, source) -> float:
	"""The order discount that is not ours. A new credit note comes with our whole share still positive,
	and with ERPNext's discount net of what earlier credit notes reversed, ours included."""
	code_discount = flt(doc.custom_code_order_discount)
	if not (doc.get("is_return") and code_discount > 0):
		return flt(doc.discount_amount) - code_discount
	reversed_by_siblings = (
		sum(abs(flt(sibling.custom_code_order_discount)) for sibling in source[1]) if source else 0
	)
	return flt(doc.discount_amount) + code_discount - reversed_by_siblings


def get_order_discount_shares(doc, order_rows: list[dict], source) -> list[float]:
	"""Each order discount in proportion to the part of the source document this one covers. The document
	that completes the source takes what is left, so the parts add up to the source's discount exactly."""
	if not source:
		return [flt(row["amount"]) for row in order_rows]

	source_doc, siblings = source
	source_total = abs(flt(source_doc.total))
	covered = abs(flt(doc.total)) + sum(abs(flt(sibling.total)) for sibling in siblings)
	is_complete = covered >= source_total - 0.005
	sign = -1 if doc.get("is_return") else 1
	precision = doc.precision("discount_amount")

	shares = []
	source_rows = get_allocations(source_doc)
	for row in order_rows:
		key = get_allocation_key(row)
		source_amount = sum(abs(flt(r["amount"])) for r in source_rows if get_allocation_key(r) == key)
		used = sum(
			abs(flt(r["amount"]))
			for sibling in siblings
			for r in get_allocations(sibling)
			if get_allocation_key(r) == key
		)
		left = max(source_amount - used, 0)
		share = left
		if not is_complete and source_total:
			share = min(left, source_amount * abs(flt(doc.total)) / source_total)
		shares.append(sign * flt(share, precision))
	return shares


def get_allocation_key(row: dict) -> tuple:
	return (row["discount_class"], row.get("discount"), row.get("code"), row.get("app"))


def get_discount_source(doc):
	"""The document this one was made from, and the other submitted documents made from it."""
	fields = ["name", "total", "custom_code_order_discount", ALLOCATIONS_FIELD]
	if doc.get("is_return"):
		if not doc.return_against:
			return None
		filters = {"return_against": doc.return_against, "is_return": 1, "name": ["!=", doc.name or ""]}
		source_doctype, source_name = doc.doctype, doc.return_against
	elif doc.doctype == "Sales Invoice":
		source_name = next((item.sales_order for item in doc.items if item.get("sales_order")), None)
		if not source_name:
			return None
		invoices = frappe.get_all(
			"Sales Invoice Item",
			filters={"sales_order": source_name, "docstatus": 1, "parent": ["!=", doc.name or ""]},
			pluck="parent",
		)
		filters = {"name": ["in", invoices], "is_return": 0} if invoices else None
		source_doctype = "Sales Order"
	else:
		source_name = next((item.prevdoc_docname for item in doc.items if item.get("prevdoc_docname")), None)
		if not source_name:
			return None
		source_doctype, filters = "Quotation", None

	source_doc = frappe.db.get_value(source_doctype, source_name, fields, as_dict=True)
	if not source_doc:
		return None
	siblings = []
	if filters:
		siblings = frappe.get_all(doc.doctype, filters={**filters, "docstatus": 1}, fields=fields)
	return source_doc, siblings


def get_shipping_allocations(doc) -> list[dict]:
	discount = doc.get("custom_shipping_discount_id")
	if not discount or not flt(doc.get("custom_shipping_discount")):
		return []
	code = next((code for code in get_discount_codes(doc) if get_code_discount(code) == discount), None)
	return [get_allocation(Selection(get_discount(discount), code), SHIPPING, doc.custom_shipping_discount)]


def cap_by_budget(discount, line_discounts: dict[int, float]) -> dict[int, float]:
	budget_left = discount.budget_left
	total = sum(line_discounts.values())
	if budget_left is None or total <= budget_left:
		return line_discounts
	return {idx: amount * budget_left / total for idx, amount in line_discounts.items()} if total else {}


def refresh_code_discounts(doc):
	"""Price an unsaved document again, such as the checkout's cash on delivery preview."""
	remove_code_discounts(doc)
	doc.calculate_taxes_and_totals()
	apply_code_discounts(doc)
