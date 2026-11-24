from frappe import _

from commera import seo
from commera.www.cart import permalink

no_cache = True


def get_context(context):
	permalink.get_context(context)
	context.cart_lines = [
		{"item_code": line["variant"]["item_code"], "qty": line["qty"]} for line in context.lines
	]
	context.seo = seo.build_page_seo({"noindex": 1}, display_name=_("Cart"))
	return context
