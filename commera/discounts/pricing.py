import math

import frappe
from frappe import _
from frappe.utils.data import flt

from commera.discounts.allocations import ALLOCATIONS_FIELD, get_allocation, get_allocations, set_allocations
from commera.discounts.cart_context import get_cart_context
from commera.discounts.codes import get_code_discount
from commera.discounts.doctype.commera_discount.commera_discount import ORDER, PRODUCT, SHIPPING
from commera.discounts.selection import (
	Selection,
	get_candidates,
	get_discount,
	get_discount_codes,
	get_unmet_reason,
)

try:
	from erpnext.accounts.services.payment_schedule import PaymentScheduleService
except ImportError:
	PaymentScheduleService = None

MAX_PRICED_COMBINATIONS = 20
# At most 3^(12/3) = 81 combinations, however many automatic discounts are live.
MAX_SEARCHED_SELECTIONS = 12


def is_storefront_cart(doc) -> bool:
	return doc.doctype == "Quotation" and doc.order_type == "Shopping Cart"


def is_repriced(doc) -> bool:
	"""Only a cart being shopped picks and prices discounts; once submitted, its amounts are the order's."""
	return doc.flags.commera_discounts is not None or (is_storefront_cart(doc) and doc.docstatus == 0)


def remove_code_discounts(doc, method=None):
	# Clamped at zero: other code may already have reset these fields.
	if doc.get("is_return"):
		return
	keep_lines = not is_repriced(doc)
	for item in doc.items:
		if flt(item.get("custom_code_discount")):
			item.discount_amount = max(flt(item.discount_amount) - flt(item.custom_code_discount), 0)
			item.rate = (flt(item.rate_with_margin) or flt(item.price_list_rate)) - item.discount_amount
		if not keep_lines:
			item.custom_code_discount = 0
			item.custom_discount = None

	if flt(doc.get("custom_code_order_discount")):
		if keep_lines:
			validate_order_discount_edit(doc)
		doc.discount_amount = max(flt(doc.discount_amount) - flt(doc.custom_code_order_discount), 0)
	doc.custom_code_order_discount = 0


def validate_order_discount_edit(doc):
	# Shown with the code discount inside; a lower figure loses staff's edit.
	previous = doc.get_doc_before_save()
	code_discount = flt(doc.custom_code_order_discount)
	if not previous or flt(previous.discount_amount) == flt(doc.discount_amount):
		return
	if flt(doc.discount_amount) < code_discount:
		frappe.throw(
			_(
				"Additional Discount Amount includes {0} from discount codes, so it cannot be less than that. "
				"To give more off, enter {0} plus the extra amount."
			).format(frappe.format_value(code_discount, {"fieldtype": "Currency"}, currency=doc.currency))
		)


def drop_copied_discounts(sales_order, method=None):
	# A Desk duplicate copies the allocations; only the first order from a cart, or its amendment, keeps them.
	if is_repriced(sales_order) or sales_order.amended_from or not get_allocations(sales_order):
		return
	quotation = next(
		(item.prevdoc_docname for item in sales_order.items if item.get("prevdoc_docname")), None
	)
	if (
		quotation
		and frappe.db.get_value("Quotation", quotation, "docstatus") == 1
		and not frappe.db.exists("Sales Order Item", {"prevdoc_docname": quotation})
	):
		return
	sales_order.flags.commera_discounts = []
	remove_code_discounts(sales_order)
	sales_order.flags.commera_discounts = None
	set_allocations(sales_order, [])


def apply_code_discounts(doc, method=None):
	if not is_repriced(doc):
		apply_recorded_discounts(doc)
		return
	selections = select_discounts(get_cart_context(doc))
	allocations = apply_line_discounts(doc, [s for s in selections if s.discount.discount_class == PRODUCT])
	doc.calculate_taxes_and_totals()
	allocations += apply_order_discount(doc, [s for s in selections if s.discount.discount_class == ORDER])
	doc.calculate_taxes_and_totals()
	allocations += get_shipping_allocations(doc)
	set_allocations(doc, allocations)
	if allocations:
		set_amounts_from_grand_total(doc)


def apply_line_discounts(doc, selections: list) -> list[dict]:
	cart = get_cart_context(doc)
	best_by_line = {}

	def offer(idx: int, amount: float, allocation: dict):
		if amount > best_by_line.get(idx, (0, None))[0]:
			best_by_line[idx] = (amount, allocation)

	for selection in selections:
		line_discounts = cap_by_budget(
			selection.discount.get_budget_left(cart), selection.discount.get_line_discounts(cart)
		)
		for idx, amount in line_discounts.items():
			offer(idx, amount, get_allocation(selection, PRODUCT, 0, idx))

	allocations = []
	for item in doc.items:
		if item.idx not in best_by_line:
			continue
		amount, allocation = best_by_line[item.idx]
		if flt(item.qty) <= 0:
			continue
		# Rounded down: a unit rate cannot carry a part of a paisa, and rounding up would overshoot a budget.
		unit_discount = round_down(
			min(amount / flt(item.qty), flt(item.rate)), item.precision("discount_amount")
		)
		add_line_discount(item, unit_discount)
		item.custom_discount = allocation["discount"]
		allocations.append({**allocation, "amount": flt(unit_discount * flt(item.qty), 2)})
	return allocations


def add_line_discount(item, unit_discount: float):
	# ERPNext rebuilds a percentage discount from the price list, which would drop this share.
	item.discount_percentage = 0
	item.discount_amount = flt(item.discount_amount) + unit_discount
	item.rate = flt(item.rate) - unit_discount
	item.custom_code_discount = unit_discount


def apply_order_discount(doc, selections: list) -> list[dict]:
	cart = get_cart_context(doc)
	offers = []
	for selection in selections:
		amount = flt(selection.discount.get_order_discount(cart))
		budget_left = selection.discount.get_budget_left(cart)
		if budget_left is not None and amount > budget_left:
			amount = round_down(budget_left, doc.precision("discount_amount"))
		offers.append((amount, get_allocation(selection, ORDER, 0)))

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
		# Inclusive tax: discount Grand Total so ERPNext works the tax out inside it.
		if not flt(doc.discount_amount):
			doc.apply_discount_on = "Grand Total" if has_inclusive_tax(doc) else "Net Total"
		# ERPNext's own percentage discount is kept as an amount, so this share can be added to it.
		doc.discount_amount = flt(doc.discount_amount) + total
		doc.additional_discount_percentage = 0
		doc.custom_code_order_discount = total
	return allocations


def get_saving(cart, selections: list) -> float:
	doc = frappe.copy_doc(cart.doc)
	doc.flags.commera_discounts = []
	remove_code_discounts(doc)
	doc.calculate_taxes_and_totals()
	allocations = apply_line_discounts(doc, [s for s in selections if s.discount.discount_class == PRODUCT])
	doc.calculate_taxes_and_totals()
	allocations += apply_order_discount(doc, [s for s in selections if s.discount.discount_class == ORDER])
	option = cart.delivery_option
	shipping = [
		s.discount.get_delivery_discount(option, cart)
		for s in selections
		if option and s.discount.discount_class == SHIPPING
	]
	return sum(flt(row["amount"]) for row in allocations) + max(shipping, default=0)


def select_discounts(cart) -> list[Selection]:
	# On a tie, the code applied first wins.
	applicable = []
	for selection in get_candidates(cart.doc):
		discount = selection.discount
		if discount.status != "Active" or not discount.is_for_currency(cart):
			continue
		if any(other.discount.name == discount.name for other in applicable):
			continue
		if get_unmet_reason(discount, cart) or not discount.gives_anything(cart):
			continue
		applicable.append(selection)

	combinations = get_combinations(get_searched_selections(applicable, cart))[:MAX_PRICED_COMBINATIONS]
	if len(combinations) == 1:
		return combinations[0]
	return max(combinations, key=lambda combination: flt(get_saving(cart, combination), 2))


def get_searched_selections(selections: list[Selection], cart) -> list[Selection]:
	# Every code the shopper typed is searched; past the cap, only the automatic discounts that save most alone.
	if len(selections) <= MAX_SEARCHED_SELECTIONS:
		return selections
	codes = [selection for selection in selections if selection.code]
	automatic = [selection for selection in selections if not selection.code]
	automatic.sort(key=lambda selection: get_solo_saving(selection.discount, cart), reverse=True)
	kept = {id(selection) for selection in codes + automatic[: MAX_SEARCHED_SELECTIONS - len(codes)]}
	return [selection for selection in selections if id(selection) in kept]


def get_solo_saving(discount, cart) -> float:
	if discount.discount_class == PRODUCT:
		return sum(discount.get_line_discounts(cart).values())
	if discount.discount_class == ORDER:
		return flt(discount.get_order_discount(cart))
	option = cart.delivery_option
	return discount.get_delivery_discount(option, cart) if option else 0.0


def get_combinations(selections: list[Selection]) -> list[list[Selection]]:
	"""Every largest set of discounts that all combine with each other, in the order the selections came."""
	order = {id(selection): index for index, selection in enumerate(selections)}

	def combines(selection, other) -> bool:
		return selection is not other and selection.discount.can_combine_with(other.discount)

	def extend(combination: list, candidates: list, skipped: list):
		if not candidates and not skipped:
			yield combination
			return
		# Bron-Kerbosch with a pivot: a set the pivot could join is found from the pivot's own branch.
		pivot = max(candidates + skipped, key=lambda other: sum(combines(other, c) for c in candidates))
		for selection in [c for c in candidates if not combines(c, pivot)]:
			yield from extend(
				[*combination, selection],
				[other for other in candidates if combines(other, selection)],
				[other for other in skipped if combines(other, selection)],
			)
			candidates.remove(selection)
			skipped.append(selection)

	combinations = [
		sorted(combination, key=lambda selection: order[id(selection)])
		for combination in extend([], list(selections), [])
	]
	return sorted(combinations, key=lambda combination: [order[id(selection)] for selection in combination])


def has_inclusive_tax(doc) -> bool:
	return any(tax.included_in_print_rate for tax in doc.get("taxes") or [])


def apply_recorded_discounts(doc):
	recorded = get_allocations(doc)
	if not recorded:
		return
	if doc.doctype == "Sales Order" and doc.docstatus == 0 and not doc.is_new():
		recorded = drop_unmet_order_discounts(doc, recorded)

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
				if row["discount_class"] == PRODUCT and row.get("discount") == item.custom_discount
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
	set_amounts_from_grand_total(doc)
	set_discount_links(doc, allocations)


def drop_unmet_order_discounts(doc, recorded: list[dict]) -> list[dict]:
	# Judged before the line discounts go back on, as the cart was.
	cart = get_cart_context(doc)
	kept = []
	for row in recorded:
		reason = row["discount_class"] == ORDER and get_discount(row["discount"]).get_unmet_minimum(cart)
		if reason:
			frappe.msgprint(
				_("{0} no longer applies to this order. {1}").format(row.get("code") or row["title"], reason)
			)
		else:
			kept.append(row)
	return kept


def set_discount_links(doc, allocations: list[dict]):
	discounts = {
		discount.name: discount
		for discount in frappe.get_all(
			"Commera Discount",
			filters={"name": ["in", list({row["discount"] for row in allocations})]},
			fields=["name", "campaign", "discount_account"],
		)
	}
	if not doc.get("utm_campaign"):
		doc.utm_campaign = next(
			(
				discounts[row["discount"]].campaign
				for row in allocations
				if discounts.get(row["discount"], {}).get("campaign")
			),
			None,
		)
	if doc.doctype != "Sales Invoice":
		return
	for item in doc.items:
		if account := discounts.get(item.get("custom_discount"), {}).get("discount_account"):
			item.discount_account = account
	order_accounts = {
		discounts[row["discount"]].discount_account
		for row in allocations
		if row["discount_class"] == ORDER and discounts.get(row["discount"], {}).get("discount_account")
	}
	if len(order_accounts) == 1 and not doc.get("additional_discount_account"):
		doc.additional_discount_account = order_accounts.pop()


def set_amounts_from_grand_total(doc):
	"""ERPNext writes these during validate, before this hook takes the discount off the total."""
	doc.set_total_in_words()
	if not doc.meta.has_field("payment_schedule") or doc.get("is_return"):
		return
	if PaymentScheduleService:
		PaymentScheduleService(doc).set_payment_schedule()
	else:
		doc.set_payment_schedule()


def get_other_order_discount(doc, source) -> float:
	# A new credit note carries our whole share; ERPNext's is net of earlier returns.
	code_discount = flt(doc.custom_code_order_discount)
	if not (doc.get("is_return") and code_discount > 0):
		return flt(doc.discount_amount) - code_discount
	reversed_by_siblings = (
		sum(abs(flt(sibling.custom_code_order_discount)) for sibling in source[1]) if source else 0
	)
	return flt(doc.discount_amount) + code_discount - reversed_by_siblings


def get_order_discount_shares(doc, order_rows: list[dict], source) -> list[float]:
	# The document completing the source takes the remainder, so parts sum exactly.
	if not source:
		return [flt(row["amount"]) for row in order_rows]

	source_doc, siblings, doc_total = source
	source_total = abs(flt(source_doc.total))
	covered = abs(doc_total) + sum(abs(flt(sibling.total)) for sibling in siblings)
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
			share = min(left, source_amount * abs(doc_total) / source_total)
		shares.append(sign * flt(share, precision))
	return shares


def get_allocation_key(row: dict) -> tuple:
	return (row["discount_class"], row.get("discount"), row.get("code"))


# The item field naming the order a delivery or invoice line comes from.
ORDER_LINK_FIELDS = {"Sales Invoice": "sales_order", "Delivery Note": "against_sales_order"}


def get_discount_source(doc):
	"""The document this one's order discount is a share of, the earlier shares of it, and this one's part."""
	fields = ["name", "total", "custom_code_order_discount", ALLOCATIONS_FIELD]
	if doc.get("is_return"):
		if not doc.return_against:
			return None
		filters = {"return_against": doc.return_against, "is_return": 1, "name": ["!=", doc.name or ""]}
		source_doctype, source_name = doc.doctype, doc.return_against
		siblings = frappe.get_all(doc.doctype, filters={**filters, "docstatus": 1}, fields=fields)
		doc_total = flt(doc.total)
	elif link_field := ORDER_LINK_FIELDS.get(doc.doctype):
		source_doctype, source_name = "Sales Order", get_discounted_order(doc, link_field)
		if not source_name:
			return None
		siblings = get_order_siblings(doc, link_field, source_name, fields)
		doc_total = sum(flt(item.amount) for item in doc.items if item.get(link_field) == source_name)
	else:
		source_name = next((item.prevdoc_docname for item in doc.items if item.get("prevdoc_docname")), None)
		if not source_name:
			return None
		source_doctype, siblings, doc_total = "Quotation", [], flt(doc.total)

	source_doc = frappe.db.get_value(source_doctype, source_name, fields, as_dict=True)
	return (source_doc, siblings, doc_total) if source_doc else None


def get_discounted_order(doc, link_field: str) -> str | None:
	orders = sorted({item.get(link_field) for item in doc.items if item.get(link_field)})
	if len(orders) <= 1:
		return orders[0] if orders else None
	discounted = frappe.get_all(
		"Sales Order", filters={"name": ["in", orders], "custom_code_order_discount": [">", 0]}, pluck="name"
	)
	if len(discounted) > 1:
		frappe.throw(
			_("Orders {0} each have a discount code order discount. Make a separate {1} for each.").format(
				", ".join(sorted(discounted)), _(doc.doctype)
			)
		)
	return discounted[0] if discounted else orders[0]


def get_order_siblings(doc, link_field: str, sales_order: str, fields: list[str]) -> list:
	# Only their lines from this order count: a combined document also carries other orders' lines.
	item_doctype = f"{doc.doctype} Item"
	lines = frappe.get_all(
		item_doctype,
		filters={link_field: sales_order, "docstatus": 1, "parenttype": doc.doctype},
		fields=["parent", "amount"],
	)
	totals = {}
	for line in lines:
		if line.parent != doc.name:
			totals[line.parent] = totals.get(line.parent, 0) + flt(line.amount)
	if not totals:
		return []
	siblings = frappe.get_all(
		doc.doctype, filters={"name": ["in", list(totals)], "is_return": 0}, fields=fields
	)
	for sibling in siblings:
		sibling.total = totals[sibling.name]
	return siblings


def get_shipping_allocations(doc) -> list[dict]:
	discount = doc.get("custom_shipping_discount_id")
	if not discount or not flt(doc.get("custom_shipping_discount")):
		return []
	code = next((code for code in get_discount_codes(doc) if get_code_discount(code) == discount), None)
	return [get_allocation(Selection(get_discount(discount), code), SHIPPING, doc.custom_shipping_discount)]


def round_down(amount: float, precision: int) -> float:
	# The epsilon keeps a float like 8.999999999 from dropping a whole paisa.
	return math.floor(flt(amount) * 10**precision + 1e-6) / 10**precision


def cap_by_budget(budget_left: float | None, line_discounts: dict[int, float]) -> dict[int, float]:
	total = sum(line_discounts.values())
	if budget_left is None or total <= budget_left:
		return line_discounts
	return {idx: amount * budget_left / total for idx, amount in line_discounts.items()} if total else {}


def refresh_code_discounts(doc):
	remove_code_discounts(doc)
	doc.calculate_taxes_and_totals()
	apply_code_discounts(doc)
