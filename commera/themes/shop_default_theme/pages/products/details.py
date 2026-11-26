from commera.www.products import details

cacheable_ssr = True
ssr_query_params = frozenset({"size"})


def get_context(context):
	details.get_context(context)
	return context
