import json

from frappe.utils.data import flt

ALLOCATIONS_FIELD = "custom_discount_allocations"


def get_allocations(doc) -> list[dict]:
	"""Each discount on a document: {discount, code, discount_class, amount}. Written only by pricing."""
	return json.loads(doc.get(ALLOCATIONS_FIELD) or "[]")


def set_allocations(doc, allocations: list[dict]):
	doc.set(ALLOCATIONS_FIELD, json.dumps(allocations) if allocations else None)


def get_allocation(selection, discount_class: str, amount: float) -> dict:
	return {
		"discount": selection.discount.name,
		"code": selection.code,
		"discount_class": discount_class,
		"amount": flt(amount, 2),
	}
