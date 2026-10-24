from commera.www.cart import cart


def get_context(context):
	cart.get_context(context)
	return context
