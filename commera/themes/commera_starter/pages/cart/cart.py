from frappe import _

from commera import seo


def get_context(context):
	context.seo = seo.build_page_seo({"noindex": 1}, display_name=_("Cart"))
	return context
