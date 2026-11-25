from commera.www.products import details

cacheable_ssr = True


def get_context(context):
	details.get_context(context)
	return context
