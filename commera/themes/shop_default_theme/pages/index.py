from commera.www import index

cacheable_ssr = True
ssr_query_params = frozenset()


def get_context(context):
	index.get_context(context)
	return context
