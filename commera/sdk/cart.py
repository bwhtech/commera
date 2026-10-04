import frappe
from frappe import _
from frappe.utils.data import flt

from commera.api.payments import cart_write_lock, save_cart_quotation, validate_cart_is_not_in_checkout
from commera.api.shipping import get_checkout_summary
from commera.checkout_hooks import apply_plugin_fees
from commera.core import _get_cart_quotation
from commera.plugin_events import get_plugin_fieldnames, validate_plugin_fieldnames
from commera.sdk.types import Cart, CheckoutSummary

__all__ = ["get_cart", "set_cart_fields"]


def get_cart() -> Cart | None:
	"""The session shopper's cart, a guest's included, or None when they have not started one."""
	quotation = _get_cart_quotation()
	if quotation.is_new():
		return None

	return {
		"name": quotation.name,
		"customer": quotation.party_name if quotation.quotation_to == "Customer" else None,
		"currency": quotation.currency,
		"items": [
			{
				"item_code": row.item_code,
				"title": row.item_name,
				"qty": flt(row.qty),
				"rate": flt(row.rate),
				"amount": flt(row.amount),
			}
			for row in quotation.items
		],
		"total": flt(quotation.total),
		"grand_total": flt(quotation.grand_total),
		"plugin_fields": {
			fieldname: quotation.get(fieldname) for fieldname in get_plugin_fieldnames("Quotation")
		},
	}


def set_cart_fields(values: dict) -> CheckoutSummary:
	"""Save an app's own Quotation fields on the shopper's cart and re-price its plugin fees. Each field must
	start with the name of an installed Commera plugin; a cart already in payment is refused."""
	validate_plugin_fieldnames("Quotation", values)
	quotation = _get_cart_quotation()
	if quotation.is_new():
		frappe.throw(_("Add something to your cart first."), frappe.DoesNotExistError)

	with cart_write_lock(quotation):
		validate_cart_is_not_in_checkout(quotation.name)
		quotation.update(values)
		apply_plugin_fees(quotation)
		save_cart_quotation(quotation)
		return get_checkout_summary(quotation)
