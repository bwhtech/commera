from commera.www.shop_web_page import index as shop_web_page


def get_context(context):
	shop_web_page.build_page_context(context)
	return context
