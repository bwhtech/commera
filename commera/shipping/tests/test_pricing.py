# Copyright (c) 2026, Build With Hussain and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.shipping.fulfilment import validate_carrier_booking
from commera.shipping.pricing import (
	UNPRICEABLE,
	get_charge_account,
	get_charge_amount,
	get_enabled_services,
	price_service,
	quote_services,
)
from commera.shipping.tests.test_carrier_import import create_test_provider_profile


def get_unique_name(label: str) -> str:
	return f"_Test {label} {frappe.generate_hash(length=8)}"


def get_company() -> str:
	return (
		frappe.defaults.get_defaults().get("company") or frappe.get_all("Company", pluck="name", limit=1)[0]
	)


def make_service(label: str, backup_charge: float = 0, **fields) -> str:
	service = frappe.get_doc(
		{
			"doctype": "Shipping Service",
			"enabled": 1,
			"title": get_unique_name(label),
			"backup_charge": backup_charge,
			**fields,
		}
	).insert(ignore_permissions=True)
	return service.name


def make_shipping_rule(conditions: list[dict], calculate_based_on: str = "Net Total", disabled: int = 0):
	company = get_company()
	rule = frappe.get_doc(
		{
			"doctype": "Shipping Rule",
			"label": get_unique_name("Store Rule"),
			"shipping_rule_type": "Selling",
			"calculate_based_on": calculate_based_on,
			"company": company,
			"account": frappe.get_all(
				"Account",
				filters={"company": company, "is_group": 0, "root_type": "Income"},
				pluck="name",
				limit=1,
			)[0],
			"cost_center": frappe.get_cached_value("Company", company, "cost_center"),
			"disabled": disabled,
			"conditions": conditions,
		}
	).insert(ignore_permissions=True)
	return rule


def band(
	service: str, from_value: float, to_value: float, shipping_amount: float = 0, free_shipping: int = 0
):
	return {
		"shipping_service": service,
		"from_value": from_value,
		"to_value": to_value,
		"shipping_amount": shipping_amount,
		"free_shipping": free_shipping,
	}


class PricingTestCase(IntegrationTestCase):
	"""No test may reach a real carrier: the demo site has live services enabled, and a live call's request
	log commits mid-test and leaks rows past the rollback."""

	def setUp(self):
		live_quotes = patch("commera.shipping.pricing.get_live_quotes", return_value={})
		self.get_live_quotes = live_quotes.start()
		self.addCleanup(live_quotes.stop)
		# The enabled-services cache outlives the class rollback, so test services must not stay in it.
		self.addCleanup(get_enabled_services.clear_cache)

	def get_quoted_amounts(self, cart: dict, shipping_rule: str | None = None) -> dict:
		rows = quote_services(None, {}, [], cart, shipping_rule=shipping_rule)
		return {row["title"]: row["amount"] for row in rows}


class TestShippingRuleBandPricing(PricingTestCase):
	def test_covering_band_prices_the_service_it_names(self):
		standard = make_service("Standard", backup_charge=99)
		rule = make_shipping_rule([band(standard, 0, 500, 40), band(standard, 500, 0, 10)])

		self.assertEqual(self.get_quoted_amounts({"base_net_total": 200}, rule.name)[standard], 40)
		self.assertEqual(self.get_quoted_amounts({"base_net_total": 800}, rule.name)[standard], 10)

	def test_band_naming_another_service_does_not_price_this_one(self):
		standard = make_service("Standard", backup_charge=99)
		express = make_service("Express", backup_charge=150)
		rule = make_shipping_rule([band(standard, 0, 500, 40)])

		amounts = self.get_quoted_amounts({"base_net_total": 200}, rule.name)

		self.assertEqual(amounts[standard], 40)
		self.assertEqual(amounts[express], 150)

	def test_band_naming_no_service_prices_nothing(self):
		standard = make_service("Standard", backup_charge=99)
		rule = make_shipping_rule([band(None, 0, 500, 40)])

		self.assertEqual(self.get_quoted_amounts({"base_net_total": 200}, rule.name)[standard], 99)

	def test_free_shipping_band_is_a_real_zero_not_dropped(self):
		standard = make_service("Standard")
		rule = make_shipping_rule([band(standard, 1000, 0, 75, free_shipping=1)])

		rows = quote_services(None, {}, [], {"base_net_total": 1500}, shipping_rule=rule.name)
		row = next(row for row in rows if row["title"] == standard)

		self.assertEqual(row["amount"], 0)
		self.assertTrue(row["is_free"])
		self.assertFalse(row["is_live_rate"])

	def test_open_ended_band_does_not_cover_a_cart_below_its_from_value(self):
		standard = make_service("Standard", backup_charge=60)
		rule = make_shipping_rule([band(standard, 1000, 0, 0, free_shipping=1)])

		self.assertEqual(self.get_quoted_amounts({"base_net_total": 999}, rule.name)[standard], 60)

	def test_weight_rule_bands_on_weight_not_value(self):
		standard = make_service("Standard", backup_charge=99)
		rule = make_shipping_rule(
			[band(standard, 0, 2, 30), band(standard, 2, 10, 80)], calculate_based_on="Net Weight"
		)

		amounts = self.get_quoted_amounts({"base_net_total": 1, "weight": 5}, rule.name)

		self.assertEqual(amounts[standard], 80)

	def test_band_amount_converts_from_company_currency(self):
		standard = make_service("Standard")
		rule = make_shipping_rule([band(standard, 0, 0, 100)])

		amounts = self.get_quoted_amounts({"base_net_total": 50, "conversion_rate": 4}, rule.name)

		self.assertEqual(amounts[standard], 25)

	def test_disabled_rule_falls_back_to_backup_charge(self):
		standard = make_service("Standard", backup_charge=99)
		rule = make_shipping_rule([band(standard, 0, 500, 40)], disabled=1)

		self.assertEqual(self.get_quoted_amounts({"base_net_total": 200}, rule.name)[standard], 99)

	def test_missing_rule_never_breaks_checkout(self):
		standard = make_service("Standard", backup_charge=99)

		amounts = self.get_quoted_amounts({"base_net_total": 200}, get_unique_name("Missing Rule"))

		self.assertEqual(amounts[standard], 99)

	def test_live_rate_prices_a_service_outside_every_band(self):
		provider = create_test_provider_profile()
		courier = make_service(
			"Courier", backup_charge=99, provider=provider, service_code="_test_code", markup_percent=10
		)
		rule = make_shipping_rule([band(courier, 0, 500, 40)])
		self.get_live_quotes.return_value = {(provider, "_test_code"): {"amount": 100}}

		rows = quote_services(None, {}, [], {"base_net_total": 800}, shipping_rule=rule.name)
		row = next(row for row in rows if row["title"] == courier)

		self.assertEqual(row["amount"], 110)
		self.assertTrue(row["is_live_rate"])


class TestUnpriceableService(PricingTestCase):
	def test_no_band_no_live_rate_no_backup_is_unpriceable(self):
		self.assertIs(price_service({"backup_charge": 0}, None, {}), UNPRICEABLE)

	def test_unpriceable_service_is_dropped_from_checkout(self):
		unpriced = make_service("Unpriced")

		self.assertNotIn(unpriced, self.get_quoted_amounts({"base_net_total": 200}))


class TestSelectedServiceCharge(PricingTestCase):
	def test_quoted_amount_wins_over_re_deriving(self):
		standard = make_service("Standard", backup_charge=99)

		self.assertEqual(get_charge_amount(standard, {}, quoted_amount=12.5), 12.5)

	def test_quoted_zero_is_honoured(self):
		standard = make_service("Standard", backup_charge=99)

		self.assertEqual(get_charge_amount(standard, {}, quoted_amount=0), 0)

	def test_covering_band_on_the_store_rule_prices_the_selection(self):
		standard = make_service("Standard", backup_charge=99)
		rule = make_shipping_rule([band(standard, 0, 500, 40)])

		self.assertEqual(get_charge_amount(standard, {"base_net_total": 200}, shipping_rule=rule.name), 40)

	def test_weight_band_prices_the_selection_by_weight(self):
		standard = make_service("Standard", backup_charge=99)
		rule = make_shipping_rule([band(standard, 0, 2, 30)], calculate_based_on="Net Weight")

		cart = {"base_net_total": 5000, "weight": 1}
		self.assertEqual(get_charge_amount(standard, cart, shipping_rule=rule.name), 30)

	def test_disabled_selection_is_still_priced(self):
		standard = make_service("Standard", backup_charge=99)
		frappe.db.set_value("Shipping Service", standard, "enabled", 0)

		self.assertEqual(get_charge_amount(standard, {}), 99)

	def test_unpriceable_selection_throws_rather_than_billing_zero(self):
		unpriced = make_service("Unpriced")

		with self.assertRaises(frappe.ValidationError):
			get_charge_amount(unpriced, {})

	def test_deleted_selection_throws_rather_than_billing_zero(self):
		with self.assertRaises(frappe.ValidationError):
			get_charge_amount(get_unique_name("Deleted"), {})


class TestChargeAccount(PricingTestCase):
	def test_account_comes_from_the_store_rule(self):
		standard = make_service("Standard")
		rule = make_shipping_rule([band(standard, 0, 500, 40)])

		self.assertEqual(get_charge_account(rule.name), rule.account)

	def test_no_rule_falls_back_to_the_callers_default(self):
		self.assertIsNone(get_charge_account(None))


class TestSelfDeliveredService(PricingTestCase):
	def test_service_without_provider_saves_while_enabled(self):
		service = make_service("Own Van", backup_charge=50)

		self.assertTrue(frappe.db.get_value("Shipping Service", service, "enabled"))

	def test_carrier_service_without_code_is_still_refused(self):
		provider = create_test_provider_profile()

		with self.assertRaises(frappe.ValidationError):
			make_service("No Code", provider=provider)

	def test_booking_refuses_an_option_the_store_delivers(self):
		service = make_service("Own Van", backup_charge=50)

		with self.assertRaises(frappe.ValidationError):
			validate_carrier_booking({"delivery_option": service, "provider": None})

	def test_booking_allows_a_carrier_option_or_no_recorded_choice(self):
		provider = create_test_provider_profile()
		courier = make_service("Courier", provider=provider, service_code="_test_code")

		validate_carrier_booking({"delivery_option": courier, "provider": provider})
		validate_carrier_booking({})
