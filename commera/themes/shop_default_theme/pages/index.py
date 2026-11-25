from commera.www import index

cacheable_ssr = True


def get_context(context):
	index.get_context(context)
	return context
