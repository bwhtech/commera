import frappe

from commera.discounts.allocations import get_allocations
from commera.discounts.codes import add_code as add_discount_code
from commera.discounts.codes import generate_codes as generate_discount_codes
from commera.discounts.preview import get_preview_quotation
from commera.sdk.types import Discount, DiscountAllocation, DiscountInput

__all__ = [
	"add_code",
	"create_discount",
	"generate_codes",
	"get_discount",
	"get_order_discounts",
	"list_discounts",
	"preview_cart",
	"update_discount",
]

DOCTYPE = "Commera Discount"


def get_discount(name: str) -> Discount:
	"""Needs read permission on Commera Discount."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	return as_discount(doc)


def list_discounts(status: str | None = None, limit: int = 100) -> list[Discount]:
	"""status is computed, so it filters after the read (may return < limit)."""
	rows = frappe.get_list(DOCTYPE, fields=["*"], order_by="creation desc", limit=limit)
	if not rows:
		return []
	names = [row.name for row in rows]
	tables = {}
	for field in frappe.get_meta(DOCTYPE).get_table_fields():
		for child in frappe.get_all(
			field.options,
			filters={"parent": ["in", names], "parenttype": DOCTYPE, "parentfield": field.fieldname},
			fields=["*"],
			order_by="idx asc",
		):
			tables.setdefault(child.parent, {}).setdefault(field.fieldname, []).append(child)
	codes = get_codes(names)
	discounts = [
		as_discount(frappe.get_doc({"doctype": DOCTYPE, **row, **tables.get(row.name, {})}), codes)
		for row in rows
	]
	return [discount for discount in discounts if not status or discount["status"] == status]


def create_discount(values: DiscountInput, code: str | None = None) -> Discount:
	doc = frappe.get_doc({"doctype": DOCTYPE, "method": "Code", **values})
	doc.flags.code = code
	doc.insert()
	return as_discount(doc)


def update_discount(name: str, values: dict) -> Discount:
	"""A table in values replaces the stored rows."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.update(values)
	doc.save()
	return as_discount(doc)


def add_code(discount: str, code: str) -> str:
	frappe.has_permission(DOCTYPE, "write", discount, throw=True)
	return add_discount_code(discount, code)


def generate_codes(discount: str, count: int, prefix: str = "") -> list[str]:
	frappe.has_permission(DOCTYPE, "write", discount, throw=True)
	return generate_discount_codes(discount, count, prefix)


def preview_cart(lines: list[dict], codes: list[str] | None = None, payment_kind: str = "prepaid") -> dict:
	flags = {"commera_payment_kind": "cod" if payment_kind == "cod" else "prepaid"}
	user = None if frappe.session.user == "Guest" else frappe.session.user
	quotation = get_preview_quotation(lines, "\n".join(codes or []), user, flags)
	return {
		"lines": [
			{
				"item_code": item.item_code,
				"qty": item.qty,
				"price": item.price_list_rate,
				"rate": item.rate,
				"amount": item.amount,
				"discount": item.custom_discount,
			}
			for item in quotation.items
		],
		"discounts": get_allocations(quotation),
		"subtotal": quotation.total,
		"total": quotation.net_total,
	}


def get_order_discounts(sales_order: str) -> list[DiscountAllocation]:
	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("read")
	return get_allocations(doc)


def get_codes(discounts: list[str]) -> dict[str, list[str]]:
	codes = {}
	if not discounts:
		return codes
	for row in frappe.get_all(
		"Commera Discount Code",
		filters={"discount": ["in", discounts]},
		fields=["name", "discount"],
		order_by="creation asc",
	):
		codes.setdefault(row.discount, []).append(row.name)
	return codes


def as_discount(doc, codes: dict[str, list[str]] | None = None) -> Discount:
	if codes is None:
		codes = get_codes([doc.name])
	return {
		**doc.as_dict(no_default_fields=True, no_child_table_fields=True),
		"name": doc.name,
		"status": doc.status,
		"discount_class": doc.discount_class,
		"codes": codes.get(doc.name, []),
	}
