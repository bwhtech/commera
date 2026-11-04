from commera.sdk.catalog import get_product_cards
from commera.www.products import details


def get_context(context):
	details.get_context(context)
	context.recommended_items = get_product_cards(context.recommended_items)
	return context
