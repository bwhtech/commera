from frappe.utils.data import flt

from commera.commera_ecommerce.doctype.commera_discount.commera_discount import ORDER, PRODUCT, SHIPPING
from commera.discounts.allocations import get_allocation, get_allocations, set_allocations
from commera.discounts.cart_context import get_cart_context
from commera.discounts.codes import get_code_discount
from commera.discounts.selection import Selection, get_discount, get_discount_codes, select_discounts


def is_storefront_cart(doc) -> bool:
	return doc.doctype == "Quotation" and doc.order_type == "Shopping Cart"


def remove_code_discounts(doc, method=None):
	"""Take the code discounts off before ERPNext prices the document again, so they never apply twice.
	Clamped at zero: other code may already have reset these fields."""
	for item in doc.items:
		if flt(item.get("custom_code_discount")):
			item.discount_amount = max(flt(item.discount_amount) - flt(item.custom_code_discount), 0)
			item.rate = (flt(item.rate_with_margin) or flt(item.price_list_rate)) - item.discount_amount
		item.custom_code_discount = 0
		item.custom_discount_code = None

	if flt(doc.get("custom_code_order_discount")):
		doc.discount_amount = max(flt(doc.discount_amount) - flt(doc.custom_code_order_discount), 0)
	doc.custom_code_order_discount = 0


def apply_code_discounts(doc, method=None):
	"""Add the discounts on top of ERPNext's price: product discounts per line (the best one wins on a
	line), then order discounts on the discounted subtotal. Apps' cart_discounts join both. A cart chooses
	its discounts again on every save; an order or invoice keeps the ones its cart had."""
	selections = get_selections(doc)
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


def get_selections(doc) -> list[Selection]:
	cart = get_cart_context(doc)
	if is_storefront_cart(doc) or doc.flags.commera_discounts is not None:
		return select_discounts(cart)
	recorded = {
		(row["discount"], row.get("code"))
		for row in get_allocations(doc)
		if row.get("discount") and row["discount_class"] != SHIPPING
	}
	return [Selection(get_discount(discount), code) for discount, code in recorded]


def get_app_discounts(doc) -> list[dict]:
	"""A cart asks the apps; an order or invoice keeps what they gave its cart, so a later change in an
	app never reprices a placed order."""
	if not is_storefront_cart(doc):
		return [row for row in get_allocations(doc) if row.get("app")]
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
		# ERPNext rebuilds a percentage discount from the price list, which would drop this share.
		item.discount_percentage = 0
		item.discount_amount = flt(item.discount_amount) + unit_discount
		item.rate = flt(item.rate) - unit_discount
		item.custom_code_discount = unit_discount
		item.custom_discount_code = allocation["discount"]
		allocations.append({**allocation, "amount": flt(unit_discount * flt(item.qty), 2)})
	return allocations


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
