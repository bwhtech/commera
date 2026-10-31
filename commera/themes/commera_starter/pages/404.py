from frappe import _

from commera import seo
from commera.sdk import catalog


def get_context(context):
	context.new_arrivals = catalog.list_products(sort="new_arrival", page_size=4)["products"]
	context.seo = seo.build_page_seo({"noindex": 1}, display_name=_("Page not found"))
	return context
