from unittest.mock import Mock, patch

import frappe

from commera.api.payments import (
	COD_PAYMENT_MODE,
	CheckoutPriceChangedError,
	confirm_payment,
	generate_quotation_for_cart,
	get_cod_total_key,
	initiate_checkout_with_mode,
	save_cart_quotation,
	update_quotation_address,
)
from commera.api.shipping import get_checkout_summary
from commera.cart_taxes import set_tax_template
from commera.core import _get_cart_quotation
from commera.tests import test_cart_checkout, test_market_taxes
from commera.tests.test_checkout_hooks import GIFT_WRAP, GIFT_WRAP_FEE
from commera.tests.test_market_taxes import GATEWAY
from commera.tests.test_payment_hooks import patch_app_hooks


class TestMarketTaxCheckout(test_market_taxes.TestMarketOrderRecords):
	create_pickup_warehouse = test_cart_checkout.TestCartCheckout.create_pickup_warehouse
	create_shop_address = test_cart_checkout.TestCartCheckout.create_shop_address
	address_payload = test_cart_checkout.TestCartCheckout.address_payload

	def enable_gateway(self):
		account = frappe.db.get_value(
			"Account", {"company": self.company, "root_type": "Income", "is_group": 0}, "name"
		)
		self.set_single("Commera Settings", "charge_account_head", account)
		frappe.flags.commera_hooks_hook_calls = []
		self.addCleanup(frappe.flags.pop, "commera_hooks_hook_calls", None)
		patch_app_hooks(
			self,
			{
				"commera_hooks": {
					"cart_fees": ["commera.tests.test_checkout_hooks.charge_gift_wrap"],
				},
			},
		)
		self.enterContext(patch("commera.api.payments.get_available_payment_modes", return_value=[GATEWAY]))
		self.enterContext(patch("commera.api.payments.resolve_payment_mode", return_value=GATEWAY))

	def checkout(self, total):
		original = frappe.get_doc
		request = frappe._dict(order_url="/paid")
		request.insert = Mock(return_value=request)

		def make_doc(*args, **kwargs):
			if args and isinstance(args[0], dict) and args[0].get("doctype") == "Gateway Payment Request":
				request.update(args[0])
				return request
			return original(*args, **kwargs)

		with patch("commera.api.payments.frappe.get_doc", side_effect=make_doc):
			initiate_checkout_with_mode(GATEWAY, expected_total=total)
		self.assertEqual(request.amount, total)

	def test_pickup_keeps_market_vat_and_plugin_fee_through_payment_and_order(self):
		template = self.make_template(10)
		self.set_market_template(template)
		self.set_single("Commera Settings", "store_pickup_enabled", 1)
		warehouse = self.create_pickup_warehouse()
		self.enable_gateway()
		self.quote_in_market()
		self.shopper = frappe.session.user

		with self.in_market():
			summary = update_quotation_address(
				{
					"is_store_pickup": True,
					"store_pickup_warehouse": warehouse,
				}
			)["checkout_summary"]
			self.assertEqual(summary["taxes"], [{"description": "VAT 10%", "amount": 30}])
			self.assertEqual(summary["plugin_fees"], [{"description": GIFT_WRAP, "amount": GIFT_WRAP_FEE}])
			self.assertEqual(summary["total"], 330 + GIFT_WRAP_FEE)
			self.checkout(summary["total"])
		quotation = _get_cart_quotation()
		frappe.set_user("Administrator")
		order = self.pay(quotation)
		self.assertEqual(order.taxes_and_charges, template)
		self.assertEqual(order.grand_total, 330 + GIFT_WRAP_FEE)
		self.assertEqual(
			[(row.description, row.tax_amount) for row in order.taxes],
			[("VAT 10%", 30), (GIFT_WRAP, GIFT_WRAP_FEE)],
		)

	def test_address_override_market_rebuild_and_payment_use_the_same_taxes(self):
		market_template, gst_template = self.make_template(10), self.make_template(18)
		self.set_market_template(market_template)
		self.enable_gateway()
		self.quote_in_market()
		self.shopper = frappe.session.user

		def gst_override(quotation):
			set_tax_template(quotation, gst_template)

		with self.in_market(), patch("commera.api.payments.set_gst_details", side_effect=gst_override):
			summary = update_quotation_address({**self.address_payload(), "shipping_same_as_billing": True})[
				"checkout_summary"
			]
			self.assertEqual(summary["total"], 330 + GIFT_WRAP_FEE)
			rebuilt = generate_quotation_for_cart({})
			self.assertEqual(rebuilt.taxes_and_charges, market_template)
			quotation = _get_cart_quotation()
			gst_override(quotation)
			save_cart_quotation(quotation)
			self.checkout(330 + GIFT_WRAP_FEE)
			self.assertEqual(get_checkout_summary(_get_cart_quotation())["total"], 330 + GIFT_WRAP_FEE)

	def test_without_a_market_template_the_address_taxes_survive_rebuild_and_payment(self):
		gst_template = self.make_template(18)
		self.enable_gateway()
		self.quote_in_market()
		self.shopper = frappe.session.user

		def gst_override(quotation):
			set_tax_template(quotation, gst_template)

		with self.in_market(), patch("commera.api.payments.set_gst_details", side_effect=gst_override):
			summary = update_quotation_address(self.address_payload())["checkout_summary"]
			self.assertEqual(summary["total"], 354 + GIFT_WRAP_FEE)
			rebuilt = generate_quotation_for_cart({})
			self.assertEqual(
				(rebuilt.taxes_and_charges, rebuilt.grand_total), (gst_template, 354 + GIFT_WRAP_FEE)
			)
			self.checkout(354 + GIFT_WRAP_FEE)

	def test_cod_confirmation_refuses_a_changed_market_tax_template(self):
		self.assert_cod_tax_refresh(clear=False)

	def test_cod_confirmation_refuses_a_cleared_market_tax_template(self):
		self.assert_cod_tax_refresh(clear=True)

	def assert_cod_tax_refresh(self, clear):
		self.set_market_template(self.make_template(10))
		self.set_single("Commera Settings", "cod_enabled", 1)
		self.set_single("Commera Settings", "cod_charge", 0)
		self.quote_in_market()
		self.shopper = frappe.session.user
		with self.in_market():
			update_quotation_address(self.address_payload())
			initiate_checkout_with_mode(COD_PAYMENT_MODE)
			quotation = _get_cart_quotation()
			self.addCleanup(frappe.cache.delete_value, get_cod_total_key(quotation.name))
			self.make_template(5, is_default=1)
			self.set_market_template(None if clear else self.make_template(18))
			with self.assertRaisesRegex(CheckoutPriceChangedError, "Please review"):
				confirm_payment(quotation.name, payment_mode=COD_PAYMENT_MODE)
			self.assertEqual(frappe.db.get_value("Quotation", quotation.name, "docstatus"), 0)
