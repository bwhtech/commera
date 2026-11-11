from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.payment_hooks import on_payment_request_update
from commera.api.payments import COD_PAYMENT_MODE, confirm_payment, generate_quotation_for_cart, place_order
from commera.cart_prices import MARKET_FIELD
from commera.localization import pin_localization, resolve
from commera.localization.address_countries import (
	AddressCountries,
	AddressCountryError,
	get_market_switches,
)
from commera.sdk import account, checkout, shop
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_market_cart import MarketCartTestCase
from commera.tests.test_markets import UAE, make_market, use_markets
from commera.utils import get_country_list, get_store_currency
from commera.www.cart.checkout import get_context

GULF = {UAE, "Saudi Arabia"}
ADDRESS = {"first_name": "ZZ", "address_line1": "1 Marina Walk", "city": "Dubai", "phone": "+971500000001"}


def in_locale(path):
	return pin_localization(resolve(path)[0])


def names(countries):
	return {country["name"] for country in countries}


class TestMarketCountryLists(IntegrationTestCase):
	"""Gulf sells to the UAE and Saudi Arabia. Benelux is disabled."""

	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar", "fr"))
		use_markets(self)
		make_market("Gulf", sorted(GULF), "ar", ["en"], handle="gulf")
		make_market("Benelux", ["Belgium", "Netherlands"], "fr", enabled=0, handle="benelux")

	def test_a_secondary_market_lists_its_own_countries(self):
		with in_locale("/en-ae/"):
			self.assertEqual(names(shop.list_countries()), GULF)

	def test_the_primary_market_lists_every_country_no_enabled_market_claims(self):
		with in_locale("/"):
			countries = names(shop.list_countries())

		self.assertFalse(countries & GULF)
		self.assertTrue({"India", "Belgium", "Netherlands"} <= countries, "Benelux is disabled")
		self.assertEqual(len(countries), len(get_country_list()) - len(GULF))

	def test_the_countries_of_other_markets_come_by_market(self):
		with in_locale("/"):
			[gulf] = shop.list_other_market_countries()
		with in_locale("/en-sa/"):
			[primary] = shop.list_other_market_countries()

		self.assertEqual((gulf["market"], gulf["title"]), ("gulf", "Gulf"))
		self.assertEqual([country["name"] for country in gulf["countries"]], ["Saudi Arabia", UAE])
		self.assertEqual(
			(primary["market"], primary["title"], primary["currency"]),
			("primary", "Other countries", get_store_currency()),
		)
		self.assertTrue({"India", "Belgium"} <= names(primary["countries"]))
		self.assertFalse(names(primary["countries"]) & GULF)

	def test_a_switch_names_the_market_and_its_currency(self):
		with in_locale("/"):
			switches = get_market_switches(shop.list_other_market_countries())

		self.assertEqual(switches["countries"], {UAE: "gulf", "Saudi Arabia": "gulf"})
		self.assertEqual(
			switches["markets"]["gulf"]["prompt"],
			f"{{0}} is in the Gulf market. Switch to shop in {get_store_currency()}?",
		)
		self.assertTrue(switches["markets"]["gulf"]["url"].startswith("/en-"))

	def test_a_switch_to_the_primary_market_names_the_current_market(self):
		with in_locale("/en-ae/"):
			switches = get_market_switches(shop.list_other_market_countries())

		self.assertEqual(switches["countries"]["India"], "primary")
		self.assertEqual(
			switches["markets"]["primary"]["prompt"],
			f"{{0}} is not in the Gulf market. Switch to shop in {get_store_currency()}?",
		)

	def test_legacy_checkout_keeps_foreign_dialing_codes(self):
		context = frappe._dict(id="shipping")
		with in_locale("/en-ae/"), patch("commera.www.cart.checkout.is_guest", return_value=True):
			get_context(context, allow_guest=True)
		self.assertEqual(names(context.country_list), GULF)
		self.assertIn("India", names(context.phone_country_list))
		html = frappe.render_template(
			'{% from "commera/templates/macros/address_form.html" import address_form %}'
			'{{ address_form(id="shipping", country_list=country_list, phone_country_list=phone_country_list) }}',
			context,
		)
		self.assertIn("+91", html)

	def test_a_blank_address_starts_in_the_country_of_the_url(self):
		with in_locale("/en-sa/"):
			self.assertEqual(AddressCountries.current().default_country(), "Saudi Arabia")

	def test_an_admin_preview_of_a_disabled_market_lists_its_countries(self):
		benelux = resolve("/fr-be/", include_unpublished=True)[0]

		with pin_localization(benelux):
			self.assertEqual(names(shop.list_countries()), {"Belgium", "Netherlands"})


class TestMarketAddressRefusal(MarketCartTestCase):
	"""The Gulf market sells to the UAE; the primary market to every other country."""

	def setUp(self):
		super().setUp()
		self.item_code = self.item("ADDRESSMARKET", market_sale=300)
		self.sign_in_shopper()
		self.add(self.item_code)

	def test_a_country_of_another_market_is_refused(self):
		with self.assertRaisesRegex(AddressCountryError, "United Arab Emirates is in the Gulf market"):
			checkout.set_addresses({**ADDRESS, "country": UAE})
		with self.in_market(), self.assertRaisesRegex(AddressCountryError, "India is not in the Gulf market"):
			checkout.set_addresses({**ADDRESS, "country": UAE}, {**ADDRESS, "country": "India"})

	def test_a_saved_address_in_another_market_is_refused(self):
		saved = account.save_address({**ADDRESS, "country": UAE})["name"]

		with self.assertRaises(AddressCountryError):
			checkout.set_addresses(saved)

	def test_a_switch_takes_the_address_and_reprices_the_cart(self):
		with self.assertRaises(AddressCountryError):
			checkout.set_addresses({**ADDRESS, "country": UAE})

		with self.in_market():
			state = checkout.set_addresses({**ADDRESS, "country": UAE})
			quotation = generate_quotation_for_cart({})

		self.assertEqual(state["billing_address"]["country"], UAE)
		self.assertEqual(quotation.get(MARKET_FIELD), "gulf")
		self.assertEqual((quotation.currency, quotation.total), (self.currency, 300))

	def test_a_disabled_markets_country_belongs_to_the_primary_market(self):
		make_market("Benelux", ["Belgium"], "en", enabled=0, handle="benelux")

		state = checkout.set_addresses({**ADDRESS, "country": "Belgium"})

		self.assertEqual(state["billing_address"]["country"], "Belgium")

	def changed_address(self, field="billing_address"):
		state = checkout.set_addresses(
			{**ADDRESS, "country": "India"},
			{**ADDRESS, "country": "India", "address_line1": "2 Shipping Street"},
		)
		frappe.db.set_value("Address", state[field]["name"], "country", UAE)
		return frappe.get_doc("Quotation", state["cart"])

	def test_payment_preparation_rechecks_a_saved_address_edited_in_the_account(self):
		saved = account.save_address({**ADDRESS, "country": "India"})["name"]
		checkout.set_addresses(saved)
		account.save_address({**ADDRESS, "country": UAE, "name": saved})
		with self.assertRaises(AddressCountryError):
			checkout.start_payment(COD_PAYMENT_MODE)

	def test_direct_cod_confirmation_rechecks_persisted_addresses(self):
		self.set_single("Commera Settings", "cod_enabled", 1)
		quotation = self.changed_address()
		with self.assertRaises(AddressCountryError):
			confirm_payment(quotation.name, payment_mode=COD_PAYMENT_MODE)
		self.assertEqual(frappe.db.get_value("Quotation", quotation.name, "docstatus"), 0)

	def test_paid_order_placement_uses_the_cart_market_without_a_request_market(self):
		quotation = self.changed_address("shipping_address")
		with self.assertRaises(AddressCountryError):
			on_payment_request_update(
				frappe._dict(
					status="Paid",
					ref_doctype="Quotation",
					ref_docname=quotation.name,
					gateway="Card",
					amount=quotation.grand_total,
					currency_code=quotation.currency,
					order_ref="zz-country-paid",
				)
			)
		self.assertEqual(frappe.db.get_value("Quotation", quotation.name, "docstatus"), 0)

	def test_repricing_into_another_market_rechecks_old_addresses(self):
		checkout.set_addresses({**ADDRESS, "country": "India"})
		with self.in_market():
			generate_quotation_for_cart({})
			with self.assertRaises(AddressCountryError):
				checkout.start_payment(COD_PAYMENT_MODE)

	def test_secondary_market_pickup_ignores_retained_delivery_but_checks_billing(self):
		self.set_single("Commera Settings", "store_pickup_enabled", 1)
		self.set_single("Commera Settings", "cod_enabled", 1)
		warehouse = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": f"ZZ Market Pickup {frappe.generate_hash(length=6)}",
				"company": frappe.defaults.get_global_default("company"),
				"custom_store_pickup": 1,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": warehouse.name,
				"address_type": "Shop",
				"address_line1": "1 Pickup Street",
				"city": "Dubai",
				"country": UAE,
				"links": [{"link_doctype": "Warehouse", "link_name": warehouse.name}],
			}
		).insert(ignore_permissions=True)
		state = checkout.set_addresses(
			{**ADDRESS, "country": "India"},
			{**ADDRESS, "country": "India", "address_line1": "2 Shipping Street"},
		)
		billing = state["billing_address"]["name"]
		account.save_address({**ADDRESS, "country": UAE, "name": billing})
		with self.in_market():
			state = checkout.set_store_pickup(warehouse.name)
			self.assertEqual(state["shipping_address"]["country"], "India")
			session = checkout.start_payment(COD_PAYMENT_MODE)
			self.assertEqual(session["reference_id"], state["cart"])
			account.save_address({**ADDRESS, "country": "India", "name": billing})
			with self.assertRaises(AddressCountryError):
				checkout.start_payment(COD_PAYMENT_MODE)

	def test_delivery_payment_checks_both_persisted_addresses(self):
		for field in ("billing_address", "shipping_address"):
			with self.subTest(field=field):
				self.changed_address(field)
				with self.assertRaises(AddressCountryError):
					checkout.start_payment(COD_PAYMENT_MODE)

	def test_a_foreign_phone_code_is_allowed_with_a_local_delivery_country(self):
		state = checkout.set_addresses({**ADDRESS, "country": "India"})
		self.assertEqual(state["shipping_address"]["phone"], ADDRESS["phone"])

	def test_guest_payment_and_direct_cod_recheck_persisted_addresses(self):
		from commera.sdk import cart
		from commera.tests.test_sdk_checkout import TestSdkCheckout

		TestSdkCheckout.allow_guest_checkout(self)
		TestSdkCheckout.send_cart_token(self, frappe.generate_hash(length=32))
		cart.add_lines([{"item_code": self.item_code, "qty": 1}])
		state = checkout.set_addresses({**ADDRESS, "country": "India"}, email="zz-country@example.com")
		frappe.db.set_value("Address", state["shipping_address"]["name"], "country", UAE)
		with self.assertRaises(AddressCountryError):
			checkout.start_payment(COD_PAYMENT_MODE)

		self.set_single("Commera Settings", "cod_enabled", 1)
		with self.assertRaises(AddressCountryError):
			confirm_payment(state["cart"], payment_mode=COD_PAYMENT_MODE)
