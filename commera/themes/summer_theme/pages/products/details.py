from commera.sdk.catalog import get_product_cards
from commera.www.products import details

cacheable_ssr = True
ssr_query_params = frozenset({"size"})


def get_context(context):
	details.get_context(context)
	context.recommended_items = get_product_cards(context.recommended_items)
	return context
