from commera.sdk.catalog import get_product_cards
from commera.www.products import list as products_list


def get_context(context):
	products_list.get_context(context)
	context.products = get_product_cards(context.products)
	return context
