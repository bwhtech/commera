import frappe

from commera import seo
from commera.sdk import shop


def get_context(context):
	page = shop.get_page(frappe.form_dict.get("route"))
	if not page:
		raise frappe.DoesNotExistError

	context.page = page
	context.seo = seo.build_page_seo(
		{
			"meta_title": page["seo"]["title"],
			"meta_description": page["seo"]["description"],
			"noindex": page["seo"]["noindex"],
		},
		display_name=page["title"],
	)
	return context
