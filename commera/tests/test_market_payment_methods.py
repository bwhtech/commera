import frappe
from bwh_payments.bwh_payments.utils import get_available_payment_modes

from commera.api.payments import (
	COD_PAYMENT_MODE,
	generate_quotation_for_cart,
	get_checkout_payment_methods,
	open_checkout,
)
from commera.sdk import checkout as checkout_sdk
from commera.tests.test_market_cart import MarketCartTestCase

ANY_CURRENCY_GATEWAY = "ZZ Any Currency Gateway"
LIMITED_GATEWAY = "ZZ Limited Currency Gateway"
# Gateways whose currencies are fixed in code. One of them takes the store currency but not the market's.
FIXED_CURRENCY_SETTINGS = ("PayU Gateway Settings", "Tabby Gateway Settings", "PayPal Gateway Settings")


class TestMarketPaymentMethods(MarketCartTestCase):
	"""The store sells in its own currency and the Gulf market in its own. One gateway takes any currency;
	the limited one takes the store currency but not the market's."""

	def setUp(self):
		super().setUp()
		self.set_single("Commera Settings", "cod_enabled", 1)
		make_gateway(ANY_CURRENCY_GATEWAY, "Stripe Gateway Settings")
		make_gateway(LIMITED_GATEWAY, find_settings(takes=self.store_currency, refuses=self.currency))
		item_code = self.item("PAYMENTS", market_sale=300)
		self.sign_in_shopper()
		self.add(item_code)

	def test_the_primary_market_keeps_every_gateway_and_cash_on_delivery(self):
		quotation = generate_quotation_for_cart({})

		self.assertEqual(quotation.currency, self.store_currency)
		self.assertEqual(
			get_checkout_payment_methods(quotation), [*get_available_payment_modes(), COD_PAYMENT_MODE]
		)
		self.assertIn(LIMITED_GATEWAY, listed_ids())

	def test_a_market_currency_the_gateway_cannot_charge_hides_it(self):
		with self.in_market():
			quotation = generate_quotation_for_cart({})
			methods = get_checkout_payment_methods(quotation)
			listed = listed_ids()

		self.assertEqual(quotation.currency, self.currency)
		self.assertNotIn(LIMITED_GATEWAY, methods)
		self.assertIn(ANY_CURRENCY_GATEWAY, methods)
		self.assertEqual(methods[-1], COD_PAYMENT_MODE)
		self.assertEqual(listed, methods)

	def test_payment_with_a_gateway_that_cannot_charge_the_market_currency_is_refused(self):
		with self.in_market():
			quotation = generate_quotation_for_cart({})
			with self.assertRaisesRegex(frappe.ValidationError, "not available for your order"):
				open_checkout(quotation, LIMITED_GATEWAY)

		self.assertFalse(frappe.db.exists("Gateway Payment Request", {"ref_docname": quotation.name}))


def make_gateway(name, settings_doctype):
	# The class shares one transaction, so an earlier test may have made it.
	if frappe.db.exists("Payment Gateway Profile", name):
		return
	frappe.get_doc(
		{
			"doctype": "Payment Gateway Profile",
			"name": name,
			"gateway_settings": settings_doctype,
			"enabled": 1,
		}
	).insert(ignore_permissions=True)


def find_settings(takes, refuses):
	for doctype in FIXED_CURRENCY_SETTINGS:
		supported = frappe.get_single(doctype).supported_currencies()
		if takes in supported and refuses not in supported:
			return doctype
	raise AssertionError(f"No gateway takes {takes} but not {refuses}")


def listed_ids():
	return [method["id"] for method in checkout_sdk.list_payment_methods()]
