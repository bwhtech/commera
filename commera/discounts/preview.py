import frappe

from commera.discounts.pricing import apply_code_discounts


def get_preview_quotation(
	lines: list[dict],
	codes: str | None = None,
	user: str | None = None,
	flags=None,
	fields: dict | None = None,
):
	"""An unsaved store cart priced as checkout would price it: ERPNext price lists and rules, then the
	discounts. Priced elevated, like the checkout cart, because ERPNext reads Items the shopper cannot."""
	# Imported here: commera.api.payments imports the cart, which imports this module.
	from commera.api.payments import system_user_session

	settings = frappe.get_cached_doc("Commera Settings")
	quotation = frappe.new_doc("Quotation")
	quotation.update(
		{
			"quotation_to": "Customer",
			"company": settings.get("company") or frappe.defaults.get_global_default("company"),
			"order_type": "Shopping Cart",
			"selling_price_list": settings.sale_price_list,
			"custom_discount_codes": codes,
			# Who is shopping, so first-order, group and once-per-customer rules can be judged.
			"party_name": user and frappe.db.get_value("Portal User", {"user": user}, "parent"),
			"contact_email": user,
		}
	)
	# Plugin fields and cart attributes, so the apps' cart hooks see the cart as checkout will.
	quotation.update(fields or {})
	quotation.flags.update(flags or {})
	for line in lines:
		quotation.append(
			"items",
			{"item_code": line["item_code"], "qty": line["qty"], "warehouse": settings.ecommerce_warehouse},
		)
	with system_user_session():
		quotation.run_method("set_missing_values")
		quotation.calculate_taxes_and_totals()
		apply_code_discounts(quotation)
	return quotation
