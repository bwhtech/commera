# Copyright (c) 2026, company@bwhstudios.com and Contributors

from unittest.mock import patch

import frappe
from bwh_payments_core.contract import PaymentGatewayBase
from frappe.model.base_document import get_controller
from frappe.tests import IntegrationTestCase
from frappe.utils.password import get_decrypted_password

from commera.api.admin.integrations import (
	describe_integration,
	get_integration_linked_doctypes,
	get_link_options,
)
from commera.api.admin.payments import get_payment_integrations, save_payment_integration
from commera.payment_gateways.connectors import get_available_payment_modes, get_connector_doctypes
from commera.tests.test_payment_hooks import patch_app_hooks

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


BUILT_IN_CARDS = [
	(
		"razorpay",
		"Razorpay",
		"Cards, UPI, netbanking and wallets. India.",
		"https://dashboard.razorpay.com/app/website-app-settings/webhooks",
	),
	("stripe", "Stripe", "Cards and wallets, worldwide.", "https://dashboard.stripe.com/apikeys"),
	(
		"telr",
		"Telr",
		"Cards and local methods across the GCC.",
		"https://telr.com/support/knowledge-base/hosted-payment-page-integration-guide/",
	),
	("tabby", "Tabby", "Buy now, pay later in four instalments. MENA.", "https://docs.tabby.ai/"),
]
PLUGIN_CONNECTOR_DOCTYPE = "Commera Settings"


class PluginConnector(PaymentGatewayBase):
	label = "Acme Pay"
	description = "A gateway from a plugin app."
	docs_url = "https://acme.example/keys"
	logo = "/assets/acme_pay/logo.svg"


def get_plugin_controller(doctype):
	return PluginConnector if doctype == PLUGIN_CONNECTOR_DOCTYPE else get_controller(doctype)


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

		self.assertEqual([card["slug"] for card in cards], ["razorpay", "stripe", "telr", "tabby"])
		for card in cards:
			self.assertTrue(card["available"], f"{card['slug']} settings doctype is missing")
			self.assertTrue(card["webhook_url"].endswith(f"gateway={card['label']}"))
			self.assertTrue(card["groups"])
			self.assertNotIn(
				"enabled",
				[field["fieldname"] for group in card["groups"] for field in group["fields"]],
			)

	def test_the_cards_come_from_the_connector_classes_in_registry_order(self):
		cards = get_payment_integrations()

		self.assertEqual(
			[(card["slug"], card["label"], card["blurb"], card["docs_url"]) for card in cards],
			BUILT_IN_CARDS,
		)
		self.assertEqual([card["logo"] for card in cards], [None] * len(BUILT_IN_CARDS))

	def test_a_connector_from_a_plugin_app_gets_a_card(self):
		patch_app_hooks(
			self,
			{"commera_hooks": {"payment_connectors": [*get_connector_doctypes(), PLUGIN_CONNECTOR_DOCTYPE]}},
		)

		with patch("commera.plugins.providers.get_controller", get_plugin_controller):
			cards = get_payment_integrations()

		self.assertEqual([card["slug"] for card in cards[:-1]], [card[0] for card in BUILT_IN_CARDS])
		plugin_card = cards[-1]
		self.assertEqual(plugin_card["slug"], "acme_pay")
		self.assertEqual(plugin_card["label"], "Acme Pay")
		self.assertEqual(plugin_card["blurb"], "A gateway from a plugin app.")
		self.assertEqual(plugin_card["docs_url"], "https://acme.example/keys")
		self.assertEqual(plugin_card["logo"], "/assets/acme_pay/logo.svg")
		self.assertTrue(plugin_card["available"])
		self.assertTrue(plugin_card["webhook_url"].endswith("gateway=Acme Pay"))

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
