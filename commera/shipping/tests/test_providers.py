import frappe
from frappe.tests import IntegrationTestCase

from commera.plugins.providers import ProviderNotRegisteredError
from commera.shipping.base_class import ShippingProviderBase
from commera.shipping.pricing import get_enabled_services, quote_services
from commera.shipping.providers import (
	PROFILE_DOCTYPE,
	disable_app_profiles,
	get_provider,
	get_provider_doctypes,
	use_providers,
	validate_providers,
)
from commera.shipping.testing import InMemoryShippingProvider
from commera.shipping.tests.test_carrier_import import create_test_provider_profile
from commera.shipping.tests.test_pricing import make_service
from commera.tests.test_payment_hooks import patch_app_hooks

BUILT_IN_CARRIERS = ["Shiprocket Shipping Settings", "AfterShip Shipping Settings"]
NOT_A_CARRIER = "Commera Settings"
ORIGIN = {"city": "Mumbai"}
DESTINATION = {"city": "Pune"}
PARCELS = [{"weight": 1.0}]


class RatesOnlyProvider(ShippingProviderBase):
	def get_rates(self, origin, destination, parcels, cod=False, declared_value=0.0):
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

	def test_a_profile_cannot_point_at_an_unregistered_doctype(self):
		profile = frappe.get_doc(
			{
				"doctype": PROFILE_DOCTYPE,
				"__newname": "_Test Not A Carrier",
				"provider_settings": NOT_A_CARRIER,
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
		self.assertEqual(carrier.rate_requests[0]["destination"], DESTINATION)

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
