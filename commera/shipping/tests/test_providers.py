import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from commera.api.admin.shipping import get_shipping_registry
from commera.plugins.providers import ProviderNotRegisteredError
from commera.shipping.base_class import RateItem, RateRequest, ShippingProviderBase
from commera.shipping.pricing import get_enabled_services, quote_services
from commera.shipping.providers import (
	PROFILE_DOCTYPE,
	disable_app_profiles,
	get_provider,
	get_provider_doctypes,
	use_providers,
	validate_providers,
)
from commera.shipping.rates import (
	FAILURE_CACHE_TTL_SECONDS,
	RATES_CACHE_PREFIX,
	get_provider_rates,
	get_request_fingerprint,
)
from commera.shipping.testing import InMemoryShippingProvider
from commera.shipping.tests.test_carrier_import import create_test_provider_profile
from commera.shipping.tests.test_pricing import make_service
from commera.tests.test_payment_hooks import patch_app_hooks

BUILT_IN_CARRIERS = ["Shiprocket Shipping Settings", "AfterShip Shipping Settings"]
CARRIER_CARDS = [("shiprocket", "Shiprocket"), ("aftership", "AfterShip")]
NOT_A_CARRIER = "Commera Settings"
ORIGIN = {"city": "Mumbai"}
DESTINATION = {"city": "Pune"}
PARCELS = [{"weight": 1.0}]


class RatesOnlyProvider(ShippingProviderBase):
	def get_rates(self, request):
		return []


def insert_unchecked_profile(name: str, provider_settings: str) -> str:
	"""A profile saved before its app was removed, which validate() would now refuse."""
	profile = frappe.new_doc(PROFILE_DOCTYPE)
	profile.name = name
	profile.provider_settings = provider_settings
	profile.enabled = 1
	profile.db_insert()
	return profile.name


class TestShippingProviderRegistry(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(get_enabled_services.clear_cache)

	def test_commera_registers_its_carriers_through_the_public_hook(self):
		self.assertEqual(get_provider_doctypes()[:2], BUILT_IN_CARRIERS)

	def test_the_integrations_screen_lists_registered_carriers_from_their_class(self):
		entries = get_shipping_registry()[:2]

		self.assertEqual([(entry["slug"], entry["label"]) for entry in entries], CARRIER_CARDS)
		self.assertTrue(all(entry["blurb"] and entry["docs_url"] for entry in entries))

	def test_an_enabled_profile_cannot_point_at_an_unregistered_doctype(self):
		profile = frappe.get_doc(
			{
				"doctype": PROFILE_DOCTYPE,
				"__newname": "_Test Not A Carrier",
				"provider_settings": NOT_A_CARRIER,
				"enabled": 1,
			}
		)

		self.assertRaises(ProviderNotRegisteredError, profile.insert)

	def test_a_declared_doctype_that_is_not_a_carrier_stops_migrate(self):
		patch_app_hooks(self, {"commera_hooks": {"shipping_providers": [*BUILT_IN_CARRIERS, NOT_A_CARRIER]}})

		with self.assertRaisesRegex(ProviderNotRegisteredError, "does not subclass"):
			validate_providers()

	def test_an_enabled_profile_whose_app_is_gone_stops_migrate(self):
		insert_unchecked_profile("_Test Orphan Carrier", NOT_A_CARRIER)

		with self.assertRaisesRegex(ProviderNotRegisteredError, "_Test Orphan Carrier"):
			validate_providers()

	def test_a_profile_whose_app_is_gone_can_still_be_disabled(self):
		profile = frappe.get_doc(
			PROFILE_DOCTYPE, insert_unchecked_profile("_Test Gone Carrier", NOT_A_CARRIER)
		)

		profile.enabled = 0
		profile.save()

		validate_providers()

	def test_uninstalling_an_app_disables_its_profiles(self):
		profile = create_test_provider_profile()

		disable_app_profiles("commera")

		self.assertEqual(frappe.db.get_value(PROFILE_DOCTYPE, profile, "enabled"), 0)


class TestInMemoryCarrier(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(get_enabled_services.clear_cache)
		self.profile = create_test_provider_profile()
		self.service = make_service(
			"Courier", backup_charge=99, provider=self.profile, service_code="express"
		)

	def quote(self) -> dict:
		rows = quote_services(ORIGIN, DESTINATION, PARCELS, {"base_net_total": 100})
		return next(row for row in rows if row["title"] == self.service)

	def test_checkout_prices_a_service_from_the_carriers_rate(self):
		carrier = InMemoryShippingProvider(rates=[{"service_code": "express", "amount": 40}])

		with use_providers({self.profile: carrier}):
			row = self.quote()

		self.assertEqual((row["amount"], row["is_live_rate"]), (40, True))
		self.assertEqual(carrier.rate_requests[0].destination, DESTINATION)

	def test_a_failing_carrier_falls_back_to_the_backup_charge(self):
		with use_providers({self.profile: InMemoryShippingProvider(fail_rates=True)}):
			row = self.quote()

		self.assertEqual((row["amount"], row["is_live_rate"]), (99, False))

	def test_only_the_listed_carriers_exist_inside_the_block(self):
		with use_providers({}):
			row = self.quote()
			self.assertRaises(ProviderNotRegisteredError, get_provider, self.profile)

		self.assertEqual((row["amount"], row["is_live_rate"]), (99, False))

	def test_the_block_restores_the_outer_carriers(self):
		carrier = InMemoryShippingProvider()

		with use_providers({self.profile: carrier}):
			with use_providers({}):
				pass
			self.assertIs(get_provider(self.profile), carrier)

	def test_only_rates_are_required(self):
		self.assertTrue(InMemoryShippingProvider.supports("booking"))
		self.assertFalse(RatesOnlyProvider.supports("booking"))
		self.assertFalse(RatesOnlyProvider.supports("tracking"))
		self.assertRaises(NotImplementedError, RatesOnlyProvider().create_shipment, {})


class TestCarrierRates(IntegrationTestCase):
	"""Carrier-calculated rates behave like Shopify's CarrierService: the carrier sees the cart, a good
	answer is reused for 15 minutes, a failure or a late answer for 30 seconds."""

	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(get_enabled_services.clear_cache)
		self.profile = create_test_provider_profile()

	def get_request(self, **fields) -> RateRequest:
		return RateRequest(origin=ORIGIN, destination=DESTINATION, parcels=PARCELS, **fields)

	def test_the_carrier_sees_the_cart_it_prices(self):
		carrier = InMemoryShippingProvider()
		shirt = RateItem("SHIRT-M", "Shirt", "SHIRT", qty=2, weight=0.3, rate=500)
		cart = {"items": [shirt], "currency": "INR", "net_total": 1000, "customer_group": "Wholesale"}
		make_service("Courier", backup_charge=99, provider=self.profile, service_code="express")

		with use_providers({self.profile: carrier}):
			quote_services(ORIGIN, DESTINATION, PARCELS, cart)

		request = carrier.rate_requests[0]
		self.assertEqual(
			(request.items, request.subtotal, request.customer_group), ([shirt], 1000, "Wholesale")
		)

	def test_a_good_answer_is_reused_and_a_failure_retried_soon(self):
		carrier = InMemoryShippingProvider(rates=[{"service_code": "express", "amount": 40}])
		broken = InMemoryShippingProvider(fail_rates=True)

		with use_providers({self.profile: carrier, "_Test Broken": broken}):
			for _attempt in range(2):
				get_provider_rates(self.profile, self.get_request())
				get_provider_rates("_Test Broken", self.get_request())
			failure_key = f"{RATES_CACHE_PREFIX}_Test Broken:{get_request_fingerprint(self.get_request())}"
			failure_ttl = frappe.cache.ttl(frappe.cache.make_key(failure_key))

		self.assertEqual((len(carrier.rate_requests), len(broken.rate_requests)), (1, 1))
		self.assertLessEqual(failure_ttl, FAILURE_CACHE_TTL_SECONDS)

	def test_saving_a_carriers_settings_drops_its_cached_rates(self):
		carrier = InMemoryShippingProvider(rates=[{"service_code": "express", "amount": 40}])

		with use_providers({self.profile: carrier}):
			get_provider_rates(self.profile, self.get_request())
			carrier.on_update()
			get_provider_rates(self.profile, self.get_request())

		self.assertEqual(len(carrier.rate_requests), 2)

	def test_an_answer_after_the_timeout_counts_as_a_failure(self):
		slow = InMemoryShippingProvider(rates=[{"service_code": "express", "amount": 40}], delay_seconds=0.05)

		with use_providers({self.profile: slow}):
			rates = get_provider_rates(self.profile, self.get_request(timeout_seconds=0))

		self.assertEqual(rates, [])

	def test_a_carrier_set_to_offer_every_rate_lists_rates_no_service_covers(self):
		frappe.db.set_value(PROFILE_DOCTYPE, self.profile, "offer_all_rates", 1)
		rates = [{"service_code": "next_day", "service_name": "Next Day", "amount": 75, "transit_days": 1}]

		with use_providers({self.profile: InMemoryShippingProvider(rates=rates)}):
			rows = quote_services(ORIGIN, DESTINATION, PARCELS, {"base_net_total": 100})

		row = next(row for row in rows if row["provider"] == self.profile)
		self.assertEqual((row["title"], row["amount"]), (f"{self.profile} Next Day", 75))
		self.assertEqual(row["min_delivery_date"], str(add_days(today(), 1)))

	def test_a_carrier_not_set_to_offer_every_rate_lists_only_its_services(self):
		rates = [{"service_code": "next_day", "service_name": "Next Day", "amount": 75}]

		with use_providers({self.profile: InMemoryShippingProvider(rates=rates)}):
			rows = quote_services(ORIGIN, DESTINATION, PARCELS, {"base_net_total": 100})

		self.assertNotIn(self.profile, [row["provider"] for row in rows])
