from frappe import _

from commera.seo import apply_title_template, default_seo

no_cache = True


def get_context(context):
	context.seo = {**default_seo(), "title": apply_title_template(_("Track order")), "noindex": True}
	return context
