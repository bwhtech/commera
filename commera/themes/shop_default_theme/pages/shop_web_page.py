from commera.www.shop_web_page import index as shop_web_page

cacheable_ssr = True
ssr_query_params = frozenset()


def get_context(context):
	if not shop_web_page.build_page_context(context):
		context.skip_ssr_cache = True
	return context
