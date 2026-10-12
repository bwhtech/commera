# Copyright (c) 2026, company@bwhstudios.com and Contributors

from unittest.mock import patch

import frappe
from bwh_payments.api import GatewayInfo, get_gateways
from bwh_payments.bwh_payments.utils import get_available_payment_modes
from frappe.tests import IntegrationTestCase
from frappe.utils.password import get_decrypted_password

from commera.api.admin.integrations import (
	describe_integration,
	get_integration_linked_doctypes,
	get_link_options,
)
from commera.api.admin.payments import (
	get_gateways_with_capability,
	get_payment_gateways,
	get_payment_integrations,
	save_payment_integration,
)

SLUG = "razorpay"
GATEWAY = "Razorpay"
SETTINGS_DOCTYPE = "Razorpay Gateway Settings"
KEY_SECRET = "zz-key-secret"
WEBHOOK_SECRET = "zz-webhook-secret"

FULL_CREDENTIALS = {
	"key_id": "rzp_test_zz",
	"key_secret": KEY_SECRET,
	"webhook_secret": WEBHOOK_SECRET,
}


def get_stored_password(fieldname):
	return get_decrypted_password(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE, fieldname, raise_exception=False)


class TestAdminPaymentIntegrations(IntegrationTestCase):
	def setUp(self):
		# IntegrationTestCase rolls back once per class, and the Single's cached copy survives rollback.
		self.addCleanup(frappe.clear_document_cache, SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)
		self.addCleanup(frappe.db.rollback)
		frappe.clear_document_cache(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)

	def get_card(self, slug=SLUG):
		return next(card for card in get_payment_integrations() if card["slug"] == slug)

	def get_field(self, card, fieldname):
		for group in card["groups"]:
			for field in group["fields"]:
				if field["fieldname"] == fieldname:
					return field

		self.fail(f"{fieldname} is not on the {card['slug']} card")

	def test_saved_credentials_read_back_without_the_secret(self):
		save_payment_integration(SLUG, 0, FULL_CREDENTIALS)

		card = self.get_card()
		self.assertEqual(self.get_field(card, "key_id")["value"], "rzp_test_zz")
		self.assertEqual(get_stored_password("key_secret"), KEY_SECRET)

		key_secret = self.get_field(card, "key_secret")
		self.assertTrue(key_secret["is_secret"])
		self.assertTrue(key_secret["is_set"])
		self.assertIsNone(key_secret["value"])
		self.assertNotIn(KEY_SECRET, frappe.as_json(card))

	def test_omitted_secret_keeps_the_stored_one(self):
		save_payment_integration(SLUG, 0, FULL_CREDENTIALS)

		save_payment_integration(SLUG, 0, {"key_id": "rzp_test_edited"})
		self.assertEqual(get_stored_password("key_secret"), KEY_SECRET)

		# The dialog submits an empty box for a secret the owner never opened.
		save_payment_integration(SLUG, 0, {"key_secret": ""})
		self.assertEqual(get_stored_password("key_secret"), KEY_SECRET)

		# An explicit null is the only "clear this" the engine honours; a required field then fails mandatory.
		with self.assertRaises(frappe.MandatoryError):
			save_payment_integration(SLUG, 0, {"key_secret": None})

	def test_enabling_with_a_required_field_blank_throws(self):
		credentials = FULL_CREDENTIALS | {"key_id": None}

		with self.assertRaises(frappe.ValidationError) as raised:
			save_payment_integration(SLUG, 1, credentials)

		self.assertIn("Key ID", str(raised.exception))
		self.assertFalse(frappe.db.get_value("Payment Gateway Profile", GATEWAY, "enabled"))

	def test_enabling_without_a_webhook_secret_is_allowed(self):
		card = save_payment_integration(SLUG, 1, {"key_id": "rzp_test_zz", "key_secret": KEY_SECRET})

		self.assertTrue(card["enabled"])
		self.assertEqual(card["missing"], [])

	def test_unknown_fieldname_throws(self):
		with self.assertRaises(frappe.ValidationError) as raised:
			save_payment_integration(SLUG, 0, {"secret_handshake": "x"})

		self.assertIn("secret_handshake", str(raised.exception))

	def test_enabling_switches_on_the_profile_and_the_payment_mode(self):
		card = save_payment_integration(SLUG, 1, FULL_CREDENTIALS)

		self.assertTrue(card["enabled"])
		self.assertTrue(card["configured"])
		self.assertEqual(card["missing"], [])

		profile = frappe.db.get_value(
			"Payment Gateway Profile", GATEWAY, ["gateway_settings", "enabled"], as_dict=True
		)
		self.assertEqual(profile.gateway_settings, SETTINGS_DOCTYPE)
		self.assertTrue(profile.enabled)
		self.assertTrue(frappe.db.get_single_value(SETTINGS_DOCTYPE, "enabled"))
		self.assertTrue(frappe.db.get_value("Mode of Payment", GATEWAY, "enabled"))
		self.assertIn(GATEWAY, get_available_payment_modes())

	def test_disabling_switches_both_off_without_deleting(self):
		save_payment_integration(SLUG, 1, FULL_CREDENTIALS)

		card = save_payment_integration(SLUG, 0, {})

		self.assertFalse(card["enabled"])
		self.assertTrue(card["configured"])
		self.assertFalse(frappe.db.get_value("Payment Gateway Profile", GATEWAY, "enabled"))
		self.assertFalse(frappe.db.get_single_value(SETTINGS_DOCTYPE, "enabled"))
		self.assertTrue(frappe.db.exists("Payment Gateway Profile", GATEWAY))
		self.assertTrue(frappe.db.exists("Mode of Payment", GATEWAY))
		self.assertNotIn(GATEWAY, get_available_payment_modes())

	def test_every_registered_gateway_is_described(self):
		cards = get_payment_integrations()

		self.assertEqual(
			[card["slug"] for card in cards], [gateway["slug"] for gateway in get_payment_gateways()]
		)
		self.assertTrue({"razorpay", "stripe", "telr", "tabby"} <= {card["slug"] for card in cards})
		for card in cards:
			self.assertTrue(card["available"], f"{card['slug']} settings doctype is missing")
			self.assertTrue(card["webhook_url"].endswith(f"gateway={card['label']}"))
			self.assertTrue(card["groups"])
			self.assertNotIn(
				"enabled",
				[field["fieldname"] for group in card["groups"] for field in group["fields"]],
			)

	def test_bwh_payments_gateways_need_no_registration_in_commera(self):
		with (
			patch("commera.api.admin.payments.get_gateways", return_value=[wallet_gateway_info()]),
			patch("commera.api.admin.payments.get_gateway_hooks", return_value=[]),
		):
			gateways = get_payment_gateways()
			reusable = get_gateways_with_capability("reusable_checkout")

		self.assertEqual(
			gateways,
			[
				{
					"slug": "test_wallet",
					"label": "Test Wallet",
					"blurb": "A wallet bwh_payments describes.",
					"settings_doctype": "Test Wallet Settings",
					"docs_url": "https://wallet.test/docs",
					"capabilities": ["reusable_checkout"],
				}
			],
		)
		self.assertEqual(reusable, ["Test Wallet"])

	def test_a_provider_app_registers_its_gateway_through_the_hook(self):
		with (
			patch("commera.api.admin.payments.get_gateways", return_value=[]),
			patch(
				"commera.api.admin.payments.get_gateway_hooks", return_value=[f"{__name__}.wallet_gateway"]
			),
		):
			gateways = get_payment_gateways()
			reusable = get_gateways_with_capability("reusable_checkout")

		self.assertEqual(gateways[-1]["slug"], "test-wallet")
		self.assertEqual(reusable, ["Test Wallet"])

	def test_a_card_from_an_app_built_for_another_commera_api_is_skipped(self):
		with (
			patch("commera.api.admin.payments.get_gateways", return_value=[]),
			patch("commera.api.admin.payments.frappe.get_hooks", return_value=[f"{__name__}.wallet_gateway"]),
			patch("commera.api.admin.payments.is_supported_app", return_value=False),
		):
			gateways = get_payment_gateways()

		self.assertNotIn("test-wallet", [gateway["slug"] for gateway in gateways])

	def test_a_failing_card_is_logged_and_skipped_instead_of_breaking_the_registry(self):
		hooks = [f"{__name__}.broken_gateway", f"{__name__}.card_without_slug", f"{__name__}.wallet_gateway"]
		with (
			patch("commera.api.admin.payments.get_gateway_hooks", return_value=hooks),
			patch("commera.api.admin.payments.frappe.log_error") as log_error,
		):
			gateways = get_payment_gateways()

		self.assertEqual(gateways[-1]["slug"], "test-wallet")
		self.assertEqual(len(gateways), len(get_gateways()) + 1)
		self.assertEqual(log_error.call_count, 2)

	def test_a_hook_cannot_replace_a_built_in_gateway(self):
		with patch(
			"commera.api.admin.payments.get_gateway_hooks", return_value=[f"{__name__}.stripe_impostor"]
		):
			gateways = get_payment_gateways()

		stripe = [gateway for gateway in gateways if gateway["slug"] == "stripe"]
		self.assertEqual(len(stripe), 1)
		self.assertEqual(stripe[0]["settings_doctype"], "Stripe Gateway Settings")

	def test_a_gateway_whose_app_is_gone_is_reported_unavailable(self):
		card = describe_integration(
			{
				"slug": "gone",
				"label": "Gone",
				"blurb": "Uninstalled provider.",
				"settings_doctype": "ZZ Missing Gateway Settings",
				"profile_doctype": "Payment Gateway Profile",
				"profile_settings_fieldname": "gateway_settings",
			}
		)

		self.assertFalse(card["available"])
		self.assertFalse(card["enabled"])
		self.assertEqual(card["groups"], [])


class TestIntegrationLinkPicker(IntegrationTestCase):
	"""A carrier quotes from its own pickup Address, so that field has to be pickable."""

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user("Administrator")

	def test_the_picker_covers_every_doctype_a_provider_setting_links_to(self):
		# Address is what makes a live rate possible at all: no origin, no quote.
		self.assertIn("Address", get_integration_linked_doctypes())

	def test_the_picker_searches_a_doctype_a_provider_links_to(self):
		options = get_link_options("Currency", search_text="INR")

		self.assertIn("INR", [option["value"] for option in options])

	def test_the_picker_refuses_a_doctype_no_provider_links_to(self):
		# Otherwise the whitelisted picker reads any doctype the session can see.
		self.assertRaises(frappe.ValidationError, get_link_options, "User")


def wallet_gateway():
	return {
		"slug": "test-wallet",
		"label": "Test Wallet",
		"blurb": "A wallet registered by another app.",
		"settings_doctype": "Test Wallet Settings",
		"docs_url": "https://wallet.test/docs",
		"capabilities": ["reusable_checkout"],
	}


def wallet_gateway_info():
	return GatewayInfo(
		name="Test Wallet",
		settings_doctype="Test Wallet Settings",
		description="A wallet bwh_payments describes.",
		docs_url="https://wallet.test/docs",
		capabilities=["reusable_checkout"],
	)


def stripe_impostor():
	return {**wallet_gateway(), "slug": "stripe", "settings_doctype": "Impostor Settings"}


def broken_gateway():
	raise RuntimeError("provider app bug")


def card_without_slug():
	return {"label": "No Slug", "settings_doctype": "No Slug Settings"}
