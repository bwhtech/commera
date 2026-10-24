from commera.www.products import list as products_list


def get_context(context):
	products_list.get_context(context)
	return context
