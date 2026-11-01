import frappe
from frappe import _

from commera import seo
from commera.sdk import account, checkout, shop

no_cache = True


def get_context(context):
	is_guest = frappe.session.user == "Guest"
	language = frappe.local.lang or "en"
	context.countries = shop.list_countries()
	context.saved_addresses = [] if is_guest else account.list_addresses()
	context.pickup_locations = checkout.list_pickup_locations()
	context.checkout_config = {
		"is_guest": is_guest,
		"email": None if is_guest else frappe.session.user,
		"country": shop.get_shop()["country"],
		"saved_addresses": [address["name"] for address in context.saved_addresses],
		"pickup_titles": {location["id"]: location["title"] for location in context.pickup_locations},
		"sign_in_url": f"/login?redirect-to=/{language}/cart/checkout",
	}
	context.seo = seo.build_page_seo({"noindex": 1}, display_name=_("Checkout"))
	return context
