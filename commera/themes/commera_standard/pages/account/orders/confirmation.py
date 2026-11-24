from frappe import _

from commera import seo

no_cache = True


def get_context(context):
	context.seo = seo.build_page_seo({"noindex": 1}, display_name=_("Order confirmed"))
	return context
