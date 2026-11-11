import json
import re
from dataclasses import replace
from unittest.mock import patch

import frappe
from frappe.api import handle
from frappe.app import make_form_dict
from frappe.auth import CookieManager
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.api.payments import generate_quotation_for_cart
from commera.cart_prices import MARKET_FIELD
from commera.localization import get_localization, pin_localization, resolve
from commera.localization.address_countries import AddressCountries
from commera.localization.resolver import get_pinned_localization
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_market_address_countries import GULF, in_locale
from commera.tests.test_market_cart import MarketCartTestCase
from commera.tests.test_markets import UAE, make_market, use_markets
from commera.themes.commera_starter.pages.account import address as starter_address
from commera.themes.commera_starter.pages.cart import checkout as starter_checkout
from commera.www.cart import checkout as legacy_checkout

CALL_SCRIPT = "commera/templates/includes/frappe-call-script.html"
# What frappe_call() adds to every request body.
PAGE_CONTEXT = re.compile(r"_lang: (?P<lang>\S+),\s+_country: (?P<country>\S+),")
LEGACY_ADDRESS = {
	"is_saved": False,
	"first_name": "ZZ",
	"last_name": "Shopper",
	"email": "zz-theme-request@example.com",
	"phone_number": "+971500000001",
	"full_address": "1 Marina Walk",
	"landmark": "Tower 2",
	"country": UAE,
	"city": "Dubai",
	"po_box": "00000",
}


class TestMarketDefaultCountry(IntegrationTestCase):
	"""Gulf sells to Saudi Arabia, then the UAE."""

	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		use_markets(self)
		make_market("Gulf", sorted(GULF), "ar", ["en"], handle="gulf")

	def test_a_secondary_market_starts_in_the_shoppers_country(self):
		with in_locale("/en-ae/"):
			self.assertEqual(AddressCountries.current().market_default_country(), UAE)

	def test_a_secondary_market_starts_in_its_first_country_without_one_of_its_own(self):
		with pin_localization(replace(resolve("/en-ae/")[0], country=None)):
			self.assertEqual(AddressCountries.current().market_default_country(), "Saudi Arabia")

	def test_the_primary_market_leaves_each_form_its_own_default(self):
		with in_locale("/"):
			self.assertIsNone(AddressCountries.current().market_default_country())
			context = self.legacy_checkout()
		self.assertEqual(context.default_country_row["name"], "Saudi Arabia")

	def test_every_theme_starts_a_gulf_address_in_the_shoppers_country(self):
		with in_locale("/en-ae/"):
			starter = starter_checkout.get_context(frappe._dict())
			book = starter_address.get_context(frappe._dict())
			legacy = self.legacy_checkout()

		self.assertEqual(starter.checkout_config["country"], UAE)
		self.assertEqual(book.default_country, UAE)
		self.assertEqual((legacy.default_country, legacy.default_country_row["name"]), (UAE, UAE))
		html = frappe.render_template(
			'{% from "commera/templates/macros/address_form.html" import address_form %}'
			"{{ address_form(id='shipping', country_list=country_list, "
			"phone_country_list=phone_country_list, default_country=default_country_row) }}",
			legacy,
		)
		self.assertIn(f'value="{UAE}"', html)

	def legacy_checkout(self):
		context = frappe._dict()
		with patch("commera.www.cart.checkout.is_guest", return_value=True):
			legacy_checkout.get_context(context, allow_guest=True)
		return context


class TestLegacyCheckoutThemeRequest(MarketCartTestCase):
	"""The legacy checkout's frappe_call() sends the page's market with each API call."""

	def setUp(self):
		super().setUp()
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
		item_code = self.item("THEMEREQUEST", market_sale=300)
		self.sign_in_shopper()
		self.add(item_code)
		self.cart = generate_quotation_for_cart({}).name

	def test_an_address_saved_from_a_gulf_checkout_prices_the_cart_in_the_gulf(self):
		self.assertEqual(frappe.db.get_value("Quotation", self.cart, MARKET_FIELD), "primary")
		page, page_context = self.open_checkout("/en-ae/cart/checkout")
		self.assertEqual(page_context["_country"], "ae")
		self.assertTrue(page.cart_needs_refresh, "the cart is still priced in the primary market")

		# The page refreshes its cart on load, then saves the address: both through frappe_call().
		refreshed = self.call_api("commera.www.cart.checkout.refresh_checkout_cart", page_context)
		self.assertEqual(refreshed.json["data"]["refreshed"], True)
		self.assertIsNone(get_pinned_localization())
		address = {
			"is_store_pickup": False,
			"billing_address": LEGACY_ADDRESS,
			"shipping_same_as_billing": True,
		}
		response = self.call_api(
			"commera.api.payments.update_quotation_address", page_context, address=address
		)

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		self.assertEqual(get_localization().market.handle, "gulf")
		quotation = frappe.get_doc("Quotation", self.cart)
		self.assertEqual((quotation.get(MARKET_FIELD), quotation.currency), ("gulf", self.currency))
		self.assertEqual(quotation.total, 300)
		self.assertEqual(frappe.db.get_value("Address", quotation.customer_address, "country"), UAE)

	def open_checkout(self, path: str) -> tuple[frappe._dict, dict]:
		"""The legacy checkout's context at `path`, and what its frappe_call() adds to a request."""
		self.visit(Request(EnvironBuilder(path=path).get_environ()))
		context = frappe._dict()
		legacy_checkout.get_context(context)
		self.assertEqual(context.default_country_row["name"], UAE)
		match = PAGE_CONTEXT.search(frappe.render_template(CALL_SCRIPT, context))
		return context, {"_lang": json.loads(match["lang"]), "_country": json.loads(match["country"])}

	def call_api(self, method: str, page_context: dict, **args):
		body = {**page_context, **args}
		request = Request(
			EnvironBuilder(path=f"/api/v2/method/{method}", method="POST", json=body).get_environ()
		)
		self.visit(request)
		make_form_dict(request)
		return handle(request)

	def visit(self, request):
		frappe.local.request = request
		frappe.local.request_ip = "127.0.0.1"
		frappe.local.cookie_manager = CookieManager()
		frappe.local.form_dict = frappe._dict()
		frappe.local.request_cache.clear()
