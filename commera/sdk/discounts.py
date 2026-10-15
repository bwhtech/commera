import frappe
from frappe import _

from commera.discounts.allocations import get_allocations
from commera.discounts.codes import add_code as add_discount_code
from commera.discounts.codes import generate_codes as generate_discount_codes
from commera.discounts.codes import normalize_code
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
	"""A discount's rules, codes and results. Needs read permission on Commera Discount."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	return as_discount(doc)


def list_discounts(status: str | None = None, limit: int = 100) -> list[Discount]:
	"""The newest `limit` discounts, keeping those with `status` when given: Active, Scheduled, Expired,
	Used Up or Disabled. Status is read from dates, switches and use, so it filters after the read."""
	names = frappe.get_list(DOCTYPE, pluck="name", order_by="creation desc", limit=limit)
	discounts = [as_discount(frappe.get_doc(DOCTYPE, name)) for name in names]
	return [discount for discount in discounts if not status or discount["status"] == status]


def create_discount(values: DiscountInput, code: str | None = None) -> Discount:
	"""Create a discount. A code discount needs `code`, the string shoppers type; an automatic one does not."""
	doc = frappe.get_doc({"doctype": DOCTYPE, "method": "Code", **values})
	if doc.method == "Code":
		if not code:
			frappe.throw(_("A code discount needs a code."))
		doc.title = doc.title or normalize_code(code)
	doc.insert()
	if code:
		add_discount_code(doc.name, code)
	return as_discount(doc)


def update_discount(name: str, values: dict) -> Discount:
	"""Change a discount's rules. A table given in `values` replaces the stored rows."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.update(values)
	doc.save()
	return as_discount(doc)


def add_code(discount: str, code: str) -> str:
	"""Add another code shoppers can type for the discount. Returns it as stored, in capitals."""
	frappe.has_permission(DOCTYPE, "write", discount, throw=True)
	return add_discount_code(discount, code)


def generate_codes(discount: str, count: int, prefix: str = "") -> list[str]:
	"""Unique single-use codes that share the discount's rules, up to 5,000 at a time."""
	frappe.has_permission(DOCTYPE, "write", discount, throw=True)
	return generate_discount_codes(discount, count, prefix)


def preview_cart(lines: list[dict], codes: list[str] | None = None, payment_kind: str = "prepaid") -> dict:
	"""Price `[{item_code, qty}]` as checkout would for the session shopper, with these codes and every
	automatic discount. Use it to show a discount's amount before checkout, for example on a landing page."""
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
				"discount": item.custom_discount_code,
			}
			for item in quotation.items
		],
		"discounts": get_allocations(quotation),
		"subtotal": quotation.total,
		"total": quotation.net_total,
	}


def get_order_discounts(sales_order: str) -> list[DiscountAllocation]:
	"""The discounts an order used and how much each gave."""
	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("read")
	return get_allocations(doc)


def as_discount(doc) -> Discount:
	return {
		**doc.as_dict(no_default_fields=True, no_child_table_fields=True),
		"name": doc.name,
		"status": doc.status,
		"discount_class": doc.discount_class,
		"codes": frappe.get_all(
			"Commera Discount Code", filters={"discount": doc.name}, pluck="name", order_by="creation asc"
		),
	}
