from commera.www.index import set_home_seo

cacheable_ssr = True
ssr_query_params = frozenset()


def get_context(context):
	set_home_seo(context)
	return context
