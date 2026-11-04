from urllib.parse import urlencode

import frappe
from frappe import _

from commera import seo


def get_context(context):
	if frappe.form_dict.get("checkout") and frappe.session.user != "Guest":
		forwarded = {
			key: value for key, value in frappe.form_dict.items() if key not in ("checkout", "lang", "cmd")
		}
		query = f"?{urlencode(forwarded)}" if forwarded else ""
		frappe.redirect(f"/{frappe.local.lang or 'en'}/cart/checkout{query}")
	context.seo = seo.build_page_seo({"noindex": 1}, display_name=_("Cart"))
	return context
