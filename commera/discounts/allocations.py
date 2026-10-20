import json

from frappe.utils.data import flt

ALLOCATIONS_FIELD = "custom_discount_allocations"


def get_allocations(doc) -> list[dict]:
	"""Each discount on a document: {discount, code, title, discount_class, amount, line}. Written
	only by pricing."""
	return json.loads(doc.get(ALLOCATIONS_FIELD) or "[]")


def set_allocations(doc, allocations: list[dict]):
	doc.set(ALLOCATIONS_FIELD, json.dumps(allocations) if allocations else None)


def get_allocation(selection, discount_class: str, amount: float, line: int | None = None) -> dict:
	"""One discount's share of a document."""
	return {
		"discount": selection.discount.name,
		"code": selection.code,
		"title": selection.discount.title,
		"discount_class": discount_class,
		"amount": flt(amount, 2),
		"line": line,
	}


def get_discount_rows(allocations: list[dict], classes: tuple = (), line: int | None = None) -> list[dict]:
	"""What each code or automatic discount took off, by the name the shopper saw it under."""
	amounts = {}
	for allocation in allocations:
		if line is not None and allocation.get("line") != line:
			continue
		if classes and allocation.get("discount_class") not in classes:
			continue
		label = allocation.get("code") or allocation.get("title")
		amounts[label] = amounts.get(label, 0) + flt(allocation.get("amount"))
	return [{"label": label, "amount": flt(amount, 2)} for label, amount in amounts.items()]


def get_order_discount_rows(doc) -> list[dict]:
	rows = get_discount_rows(get_allocations(doc), ("Order",))
	# A discount ERPNext gave on its own, such as a Pricing Rule, has no allocation to name it.
	other = flt(flt(doc.get("discount_amount")) - sum(row["amount"] for row in rows), 2)
	return [*rows, {"label": None, "amount": other}] if other > 0 else rows


def get_price_discount_rows(doc) -> list[dict]:
	"""Every discount off the goods, line and order, so a summary that starts from list prices adds up."""
	return get_discount_rows(get_allocations(doc), ("Product",)) + get_order_discount_rows(doc)
