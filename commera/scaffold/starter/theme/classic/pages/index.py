from commera.www.index import set_home_seo


def get_context(context):
	# The canonical, hreflang and share tags of the home page.
	set_home_seo(context)
	return context
