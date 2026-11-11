import frappe
from frappe import _

from commera import seo
from commera.localization.address_countries import AddressCountries, get_market_switches
from commera.sdk import account, checkout, shop
from commera.sdk.format import url

no_cache = True


def get_context(context):
	is_guest = frappe.session.user == "Guest"
	context.countries = shop.list_countries()
	context.other_markets = shop.list_other_market_countries()
	context.saved_addresses = [] if is_guest else account.list_addresses()
	context.pickup_locations = checkout.list_pickup_locations()
	country_titles = {country["name"]: country["title"] for country in context.countries}
	for address in context.saved_addresses:
		country = address["country"]
		country_titles[country] = _(country)
	context.checkout_config = {
		"is_guest": is_guest,
		"email": None if is_guest else frappe.session.user,
		"country": AddressCountries.current().default_country(),
		"country_titles": country_titles,
		"saved_addresses": [address["name"] for address in context.saved_addresses],
		"saved_countries": {address["name"]: address["country"] for address in context.saved_addresses},
		"market_switches": get_market_switches(context.other_markets),
		"pickup_titles": {location["id"]: location["title"] for location in context.pickup_locations},
		"sign_in_url": f"{url('/account/login')}?redirect-to={url('/cart/checkout')}",
	}
	context.seo = seo.build_page_seo(
		{"noindex": 1}, display_name=_("Checkout", context="Storefront checkout")
	)
	return context
