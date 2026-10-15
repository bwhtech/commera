import json

from frappe.utils.data import flt

ALLOCATIONS_FIELD = "custom_discount_allocations"


def get_allocations(doc) -> list[dict]:
	"""Each discount on a document: {discount, code, app, title, discount_class, amount, line}. Written
	only by pricing."""
	return json.loads(doc.get(ALLOCATIONS_FIELD) or "[]")


def set_allocations(doc, allocations: list[dict]):
	doc.set(ALLOCATIONS_FIELD, json.dumps(allocations) if allocations else None)


def get_allocation(selection, discount_class: str, amount: float, line: int | None = None) -> dict:
	"""One discount's share of a document. `app` names the plugin a cart_discounts hook came from; a
	merchant's discount has none."""
	return {
		"discount": selection.discount.name,
		"code": selection.code,
		"app": None,
		"title": selection.discount.title,
		"discount_class": discount_class,
		"amount": flt(amount, 2),
		"line": line,
	}
