from frappe import _

from commera.localization.address_countries import AddressCountries, get_market_switches
from commera.sdk import shop
from commera.seo import apply_title_template, default_seo

no_cache = True


def get_context(context):
	context.seo = {**default_seo(), "title": apply_title_template(_("Addresses")), "noindex": True}
	context.countries = shop.list_countries()
	context.other_markets = shop.list_other_market_countries()
	context.market_switches = get_market_switches(context.other_markets)
	context.default_country = AddressCountries.current().market_default_country()
	return context
