# The store's own charges at checkout: the Shipping Rule, the cash on delivery fee and delivery option fees.

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.payments import COD_PAYMENT_MODE, generate_quotation_for_cart, save_cart_quotation
from commera.api.shipping import add_cod_charge, get_checkout_summary, get_cod_charge
from commera.core import _get_cart_quotation, get_party
from commera.sdk import cart as cart_sdk
from commera.sdk import checkout
from commera.shipping.pricing import get_live_amount, price_service
from commera.tests import test_cart_checkout, test_plugin_events
from commera.tests.test_admin_orders import ensure_fiscal_year
from commera.tests.test_market_cart import MarketCartTestCase
from commera.tests.test_sdk_checkout import BILLING_ADDRESS
from commera.utils import get_store_company

SHIPPING_AMOUNT = 25
COD_FEE = 15
KUWAIT_ADDRESS = {**BILLING_ADDRESS, "city": "Kuwait City", "country": "Kuwait", "phone": "+96550000001"}


class ShippingRuleTestCase(IntegrationTestCase):
	"""A store whose Shipping Rule charges a flat 25 to Saudi Arabia only, with cash on delivery on."""

	create_shopper = test_cart_checkout.TestCartCheckout.create_shopper
	create_item = test_cart_checkout.TestCartCheckout.create_item
	list_item = test_plugin_events.TestPluginEvents.list_item

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Another test class can leave the cache holding settings that its rollback undid.
		frappe.clear_document_cache("Commera Settings", "Commera Settings")
		commera_settings = frappe.get_cached_doc("Commera Settings")
		cls.default_price_list = commera_settings.get_default_price_list()
		cls.sale_price_list = commera_settings.get_sale_price_list()
		cls.warehouse = commera_settings.ecommerce_warehouse
		ensure_fiscal_year()

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(frappe.clear_document_cache, "Commera Settings", "Commera Settings")
		frappe.cache.delete_keys("rl:*127.0.0.1*")
		self.company = get_store_company()
		self.rule_account, self.charge_account = frappe.get_all(
			"Account",
			{"company": self.company, "root_type": "Income", "is_group": 0},
			pluck="name",
			limit=2,
		)
		self.rule = self.make_rule()
		self.set_settings(
			shipping_rule=self.rule.name,
			charge_account_head=self.charge_account,
			cod_enabled=1,
			cod_charge=COD_FEE,
			cod_charge_applicable_below=100000,
		)
		self.shopper = self.create_shopper()
		self.item = self.create_item(sale_rate=test_cart_checkout.SALE_RATE)
		self.list_item(self.item)

	def make_rule(self):
		return frappe.get_doc(
			{
				"doctype": "Shipping Rule",
				"label": f"ZZ Saudi Delivery {frappe.generate_hash(length=6)}",
				"shipping_rule_type": "Selling",
				"company": self.company,
				"account": self.rule_account,
				"cost_center": frappe.get_cached_value("Company", self.company, "cost_center"),
				"calculate_based_on": "Fixed",
				"shipping_amount": SHIPPING_AMOUNT,
				"countries": [{"country": "Saudi Arabia"}],
			}
		).insert(ignore_permissions=True)

	def set_settings(self, **values):
		frappe.db.set_single_value("Commera Settings", values)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

	def fill_cart(self):
		frappe.set_user(self.shopper)
		cart_sdk.add_lines([{"item_code": self.item, "qty": 1}])


class TestCashOnDeliveryAccount(ShippingRuleTestCase):
	def test_settings_accept_the_shipping_rules_account_for_charges(self):
		settings = frappe.get_doc("Commera Settings")
		settings.charge_account_head = self.rule_account
		settings.save(ignore_permissions=True)

	def test_cod_on_the_shipping_account_survives_save_submit_and_mapping(self):
		self.set_settings(charge_account_head=self.rule_account)
		self.fill_cart()
		state = checkout.set_addresses(BILLING_ADDRESS)
		summary = state["summary"]["cash_on_delivery"]
		self.assertEqual((summary["shipping"], summary["cod_charge"]), (SHIPPING_AMOUNT, COD_FEE))
		session = checkout.start_payment(COD_PAYMENT_MODE, summary["total"])
		order = checkout.complete(session["reference_id"])["order"]
		self.assertEqual(order["grand_total"], summary["total"])
		rows = frappe.get_doc("Sales Order", order["name"]).taxes
		self.assertEqual([row.tax_amount for row in rows], [COD_FEE, SHIPPING_AMOUNT])
		self.assertEqual([row.commera_cart_charge for row in rows], ["cod", "shipping_rule"])

	def test_missing_shipping_row_is_created_before_cod_recalculation(self):
		from commera.api.shipping import remove_shipping_rule_row

		self.fill_cart()
		checkout.set_addresses(BILLING_ADDRESS)
		quotation = _get_cart_quotation()
		remove_shipping_rule_row(quotation)
		add_cod_charge(quotation, COD_FEE, self.rule_account)
		self.assertEqual([row.tax_amount for row in quotation.taxes], [COD_FEE, SHIPPING_AMOUNT])
		save_cart_quotation(quotation)
		self.assertEqual([row.tax_amount for row in quotation.taxes], [COD_FEE, SHIPPING_AMOUNT])

	def test_a_saved_shipping_row_without_its_marker_is_not_added_twice(self):
		self.fill_cart()
		checkout.set_addresses(BILLING_ADDRESS)
		quotation = _get_cart_quotation()
		for row in quotation.taxes:
			row.commera_cart_charge = None
		add_cod_charge(quotation, COD_FEE, self.rule_account)
		self.assertEqual([row.tax_amount for row in quotation.taxes], [COD_FEE, SHIPPING_AMOUNT])

	def test_plugin_fees_stay_before_shipping_after_a_template_refresh(self):
		from commera.cart_taxes import set_tax_template
		from commera.checkout_hooks import apply_plugin_fees

		self.fill_cart()
		checkout.set_addresses(BILLING_ADDRESS)
		quotation = _get_cart_quotation()
		fee = {"description": "App fee", "account_head": self.rule_account, "amount": 7}
		with (
			patch("commera.checkout_hooks.get_handlers", return_value=["test.fee"]),
			patch("frappe.get_attr", return_value=lambda quotation: [fee]),
		):
			apply_plugin_fees(quotation)
		self.assertEqual([row.tax_amount for row in quotation.taxes], [7, SHIPPING_AMOUNT])
		add_cod_charge(quotation, COD_FEE, self.rule_account)
		template_row = {
			"charge_type": "Actual",
			"account_head": self.rule_account,
			"description": "Template levy",
			"tax_amount": 3,
			"included_in_print_rate": 0,
		}
		with patch("commera.cart_taxes.get_template_rows", return_value=[template_row]):
			set_tax_template(quotation, None)
		quotation.calculate_taxes_and_totals()
		self.assertEqual([row.tax_amount for row in quotation.taxes], [3, 7, COD_FEE, SHIPPING_AMOUNT])
		self.assertEqual(
			[row.commera_cart_charge for row in quotation.taxes], [None, None, "cod", "shipping_rule"]
		)

	def test_the_previewed_cod_fee_row_is_the_row_that_is_saved(self):
		self.fill_cart()
		checkout.set_addresses(BILLING_ADDRESS)
		quotation = _get_cart_quotation()

		add_cod_charge(quotation, COD_FEE, self.charge_account)
		previewed = [(row.account_head, row.cost_center, row.tax_amount) for row in quotation.taxes]
		save_cart_quotation(quotation)

		self.assertEqual(
			[(row.account_head, row.cost_center, row.tax_amount) for row in quotation.taxes], previewed
		)

	def test_a_cod_order_below_the_threshold_is_placed_at_its_previewed_total(self):
		self.fill_cart()
		state = checkout.set_addresses(BILLING_ADDRESS)
		cod_summary = state["summary"]["cash_on_delivery"]
		self.assertEqual((cod_summary["shipping"], cod_summary["cod_charge"]), (SHIPPING_AMOUNT, COD_FEE))

		session = checkout.start_payment(COD_PAYMENT_MODE, cod_summary["total"])
		order = checkout.complete(session["reference_id"])["order"]

		self.assertEqual(order["grand_total"], cod_summary["total"])
		charges = frappe.get_all(
			"Sales Taxes and Charges",
			{"parent": order["name"], "charge_type": "Actual"},
			pluck="tax_amount",
			order_by="idx",
		)
		self.assertEqual(charges, [COD_FEE, SHIPPING_AMOUNT])


class TestShippingRuleCountries(ShippingRuleTestCase):
	def test_an_address_the_rule_does_not_deliver_to_saves_with_no_delivery_and_no_payment(self):
		self.fill_cart()

		state = checkout.set_addresses(KUWAIT_ADDRESS)

		self.assertEqual(state["shipping_address"]["country"], "Kuwait")
		self.assertEqual(state["summary"]["shipping"], 0)
		self.assertEqual(checkout.list_shipping_options()["reason"], "unavailable")
		self.assertEqual(checkout.list_payment_methods(), [])
		with self.assertRaisesRegex(frappe.ValidationError, "We do not deliver to Kuwait"):
			checkout.start_payment(COD_PAYMENT_MODE, state["summary"]["cash_on_delivery"]["total"])

	def test_a_saved_address_the_rule_does_not_deliver_to_does_not_break_the_cart(self):
		self.fill_cart()
		saved = checkout.set_addresses(KUWAIT_ADDRESS)["shipping_address"]["name"]

		state = checkout.set_addresses(saved)

		self.assertEqual(state["shipping_address"]["name"], saved)
		self.assertEqual(checkout.get()["summary"]["shipping"], 0)

	def test_a_default_address_outside_the_rule_does_not_block_a_saudi_address(self):
		self.save_default_address("Egypt")
		self.fill_cart()

		state = checkout.set_addresses(BILLING_ADDRESS)

		self.assertEqual(state["summary"]["shipping"], SHIPPING_AMOUNT)
		self.assertEqual(checkout.list_payment_methods()[-1]["id"], COD_PAYMENT_MODE)

	def save_default_address(self, country: str):
		frappe.set_user(self.shopper)
		party = get_party().name
		frappe.set_user("Administrator")
		address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": "ZZ Default",
				"address_type": "Shipping",
				"address_line1": "1 Tahrir Square",
				"city": "Cairo",
				"country": country,
				"is_primary_address": 1,
				"is_shipping_address": 1,
				"links": [{"link_doctype": "Customer", "link_name": party}],
			}
		)
		address.insert(ignore_permissions=True)


class TestContactAfterSignup(ShippingRuleTestCase):
	def test_the_address_step_locks_the_contact_that_the_signup_job_also_saves(self):
		# Frappe's User.on_update enqueues create_contact, which re-saves this Contact right after sign-up.
		self.fill_cart()
		get_doc = frappe.get_doc

		with patch("frappe.get_doc", wraps=get_doc) as spy:
			checkout.set_addresses(BILLING_ADDRESS)

		contact_loads = [call for call in spy.call_args_list if call.args[:1] == ("Contact",)]
		self.assertTrue(contact_loads)
		self.assertTrue(all(call.kwargs.get("for_update") for call in contact_loads))


class TestChargesInTheCartCurrency(MarketCartTestCase):
	"""The Gulf market's currency is worth 20 of the store's. Fees are set in the store's currency."""

	def setUp(self):
		super().setUp()
		self.set_single("Commera Settings", "shipping_rule", None)
		self.item_code = self.item("FEES", market_sale=300)

	def quote_in_market(self):
		self.sign_in_shopper()
		with self.in_market():
			self.add(self.item_code)
			return generate_quotation_for_cart({})

	def test_the_cod_fee_is_converted_to_the_cart_currency(self):
		self.set_single("Commera Settings", "cod_charge", COD_FEE)
		self.set_single("Commera Settings", "cod_charge_applicable_below", 100000)

		self.assertEqual(get_cod_charge(self.quote_in_market()), 0.75)

	def test_the_cod_threshold_is_judged_in_the_store_currency(self):
		# 300 in the cart currency is 6000 in the store's, above the threshold of 500.
		self.set_single("Commera Settings", "cod_charge", COD_FEE)
		self.set_single("Commera Settings", "cod_charge_applicable_below", 500)
		quotation = self.quote_in_market()

		self.assertEqual(get_cod_charge(quotation), 0)
		self.assertEqual(get_checkout_summary(quotation)["cash_on_delivery"]["cod_charge"], 0)


CART_AT_20 = {"currency": "AED", "conversion_rate": 20}


class TestDeliveryOptionFeesInTheCartCurrency(IntegrationTestCase):
	def test_a_backup_charge_is_converted_to_the_cart_currency(self):
		self.assertEqual(price_service({"backup_charge": 35}, None, CART_AT_20), (1.75, False))

	def test_a_handling_fee_is_converted_to_the_cart_currency(self):
		quote = {"amount": 10, "currency": "AED"}

		self.assertEqual(get_live_amount({"handling_fee": 20}, quote, CART_AT_20), 11)
