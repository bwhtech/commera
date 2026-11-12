from unittest.mock import Mock, patch

import frappe
from frappe.model.meta import Meta

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

	def address_payload(self):
		payload = test_cart_checkout.TestCartCheckout.address_payload(self)
		payload["billing_address"].update({"country": "United Arab Emirates", "city": "Dubai"})
		return payload

	def test_inclusive_summaries_before_and_after_address(self):
		self.assert_public_summaries(inclusive=True)

	def test_exclusive_summaries_before_and_after_address(self):
		self.assert_public_summaries(inclusive=False)

	def test_inclusive_delivery_named_template_stays_tax(self):
		self.assert_public_summaries(inclusive=True, description="Delivery Charges - template levy")

	def test_inclusive_summary_uses_discounted_vat(self):
		self.assert_public_summaries(inclusive=True, discount=70)

	def test_inclusive_cod_summary_uses_server_rounding(self):
		self.assert_public_summaries(inclusive=True, delivery=10.25, cod=5.25)

	def assert_public_summaries(self, inclusive, description=None, discount=0, delivery=0, cod=0):
		from commera.api.storefront import cart as cart_api
		from commera.api.storefront import checkout as checkout_api
		from commera.tests.test_sdk_checkout import BILLING_ADDRESS

		template = self.make_template(15, inclusive=int(inclusive))
		if description:
			doc = frappe.get_doc("Sales Taxes and Charges Template", template)
			doc.taxes[0].description = description
			doc.save(ignore_permissions=True)
		self.set_market_template(template)
		if cod:
			account = frappe.db.get_value(
				"Account", {"company": self.company, "root_type": "Income", "is_group": 0}, "name"
			)
			self.set_single("Commera Settings", "charge_account_head", account)
			self.set_single("Commera Settings", "cod_enabled", 1)
			self.set_single("Commera Settings", "cod_charge", cod)
			self.set_single("Commera Settings", "cod_charge_applicable_below", 100000)
		self.item_code = self.item("SUMMARY", market_sale=699.95)
		code = (
			self.make_code(
				discount_type="Amount Off Order",
				value_type="Fixed Amount",
				value=discount,
				currency=self.currency,
			)
			if discount
			else None
		)
		self.sign_in_shopper()
		frappe.local.request_ip = "127.0.0.1"
		with self.in_market():
			priced = cart_api.add_lines([{"item_code": self.item_code, "qty": 1}])
			self.assertEqual(priced["subtotal"], 699.95)
			self.assertEqual(priced["total"], 700 if inclusive else 699.95)
			self.assertIsNone(checkout_api.get())
			if inclusive:
				self.assertEqual(priced["items_total"], 699.95)
				self.assertEqual(
					priced["taxes"][0]["description"], (description or "VAT 15%") + " (included)"
				)
			state = checkout_api.set_addresses(
				{**BILLING_ADDRESS, "country": "United Arab Emirates", "city": "Dubai"}
			)
			if discount:
				priced = cart_api.add_discount_code(code)
				state = checkout_api.get()
			if delivery:
				with patch(
					"commera.api.shipping.get_delivery_options",
					return_value=[{"title": "Express", "amount": delivery}],
				):
					state = checkout_api.set_shipping_option("Express")
			summary = state["summary"]
			quotation = _get_cart_quotation()
			self.assertEqual(
				summary["total"], 710 if delivery else (630 if discount else (700 if inclusive else 805))
			)
			self.assertEqual(summary["subtotal"], 699.95)
			self.assertEqual(summary["total"], quotation.rounded_total or quotation.grand_total)
			self.assertEqual(
				summary["taxes"][0]["description"],
				(description or "VAT 15%") + (" (included)" if inclusive else ""),
			)
			self.assertEqual(summary["shipping"], delivery)
			if inclusive:
				self.assertTrue(summary["taxes"][0]["included"])
				self.assertEqual(summary["taxes"][0]["amount"], 82.17 if discount else 91.30)
			self.assertAlmostEqual(
				summary["subtotal"]
				+ summary["shipping"]
				- summary["discount_amount"]
				+ sum(row["amount"] for row in summary["taxes"] if not row.get("included"))
				+ summary["rounding_adjustment"],
				summary["total"],
				places=2,
			)
			if discount:
				self.assertEqual(
					summary["taxes"][0]["amount"], quotation.taxes[0].tax_amount_after_discount_amount
				)
			if cod:
				self.assertEqual(summary["cash_on_delivery"]["total"], 715)
				self.assertEqual(summary["cash_on_delivery"]["cod_charge"], cod)
			self.assertEqual(checkout_api.get()["summary"], summary)
			self.assertEqual(cart_api.get_cart()["total"], priced["total"])

	def enable_gateway(self):
		account = frappe.db.get_value(
			"Account", {"company": self.company, "root_type": "Income", "is_group": 0}, "name"
		)
		self.set_single("Commera Settings", "charge_account_head", account)
		# A card payment is invoiced in the market currency on the store-currency receivable.
		self.set_single("Accounts Settings", "allow_multi_currency_invoices_against_single_party_account", 1)
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
		self.enterContext(
			patch("commera.api.payments.get_gateway_options", return_value=[frappe._dict(name=GATEWAY)])
		)
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


class TestLegacyMarketTaxCheckout(test_market_taxes.MarketTaxTestCase):
	create_pickup_warehouse = test_cart_checkout.TestCartCheckout.create_pickup_warehouse
	create_shop_address = test_cart_checkout.TestCartCheckout.create_shop_address

	def test_primary_legacy_shipping_survives_reload_without_duplication(self):
		self.assert_legacy_checkout()

	def test_primary_shipping_before_marker_migration(self):
		self.assert_without_marker_field()

	def test_primary_colliding_template_before_marker_migration(self):
		self.assert_without_marker_field(colliding=True)

	def test_primary_identical_template_rows_before_marker_migration(self):
		self.assert_without_marker_field(colliding=True, template_copies=2)

	def assert_without_marker_field(self, colliding=False, template_copies=1):
		# Patch the class: saves read the cached valid fields of whichever meta object is current.
		def drop_marker(original):
			def wrapper(meta):
				names = original(meta)
				if meta.name != "Sales Taxes and Charges":
					return names
				return [name for name in names if name != "commera_cart_charge"]

			return wrapper

		with (
			patch.object(Meta, "get_valid_fields", drop_marker(Meta.get_valid_fields)),
			patch.object(Meta, "get_valid_columns", drop_marker(Meta.get_valid_columns)),
		):
			self.assert_legacy_checkout(colliding=colliding, absent=True, template_copies=template_copies)

	def test_primary_colliding_template_survives_legacy_checkout(self):
		self.assert_legacy_checkout(colliding=True)

	def assert_legacy_checkout(self, colliding=False, absent=False, template_copies=1):
		from commera.api.shipping import set_delivery_option
		from commera.cart_taxes import TEMPLATE_DOCTYPE

		rule = frappe.get_doc(
			{
				"doctype": "Shipping Rule",
				"label": f"ZZ Legacy Shipping {frappe.generate_hash(length=8)}",
				"shipping_rule_type": "Selling",
				"company": self.company,
				"account": self.account,
				"calculate_based_on": "Fixed",
				"shipping_amount": 40,
			}
		).insert(ignore_permissions=True)
		self.set_single("Commera Settings", "shipping_rule", rule.name)
		self.set_single("Commera Settings", "store_pickup_enabled", 1)
		warehouse = self.create_pickup_warehouse()
		template = None
		if colliding:
			template = self.make_template(0)
			doc = frappe.get_doc(TEMPLATE_DOCTYPE, template)
			doc.taxes[0].update({"charge_type": "Actual", "description": rule.label, "tax_amount": 40})
			for _ in range(template_copies - 1):
				doc.append(
					"taxes",
					{
						key: doc.taxes[0].get(key)
						for key in (
							"charge_type",
							"account_head",
							"description",
							"tax_amount",
							"included_in_print_rate",
						)
					},
				)
			doc.save(ignore_permissions=True)
		self.sign_in_shopper()
		self.add(self.item_code)
		generate_quotation_for_cart({})
		quotation = _get_cart_quotation()
		if template:
			set_tax_template(quotation, template)
		for row in quotation.taxes:
			row.set("commera_cart_charge", None)
		save_cart_quotation(quotation)
		quotation = frappe.get_doc("Quotation", quotation.name)
		self.assertTrue(all(not row.get("commera_cart_charge") for row in quotation.taxes))
		extra = 40 * template_copies if colliding else 0
		for _ in range(2):
			rebuilt = generate_quotation_for_cart({})
			self.assertEqual(rebuilt.grand_total, 120 + extra)
			self.assertEqual(len(rebuilt.taxes), template_copies + 1 if colliding else 1)
			if absent:
				reloaded = frappe.get_doc("Quotation", rebuilt.name)
				self.assertTrue(all(not row.get("commera_cart_charge") for row in reloaded.taxes))
		with patch(
			"commera.api.shipping.get_delivery_options",
			return_value=[{"title": "Legacy express", "amount": 40}],
		):
			for _ in range(2):
				summary = set_delivery_option("Legacy express")["checkout_summary"]
				self.assertEqual(summary["total"], 120 + extra)
				self.assertEqual(summary["shipping"], 40)
				self.assertEqual(len(summary["taxes"]), template_copies if colliding else 0)
				self.assertEqual(len(_get_cart_quotation().taxes), template_copies + 1 if colliding else 1)
				quotation = _get_cart_quotation()
				for row in quotation.taxes:
					row.set("commera_cart_charge", None)
				save_cart_quotation(quotation)
		from commera.api.shipping import add_cod_charge

		quotation = _get_cart_quotation()
		self.set_single("Commera Settings", "charge_account_head", self.account)
		add_cod_charge(quotation, 15, self.account)
		for row in quotation.taxes:
			row.set("commera_cart_charge", None)
		add_cod_charge(quotation, 15, self.account)
		self.assertEqual(quotation.grand_total, 135 + extra)
		for row in quotation.taxes:
			row.set("commera_cart_charge", None)
		save_cart_quotation(quotation)
		summary = update_quotation_address({"is_store_pickup": True, "store_pickup_warehouse": warehouse})[
			"checkout_summary"
		]
		self.assertEqual(summary["total"], 80 + extra)
		from commera.api.payments import update_delivery_charges

		quotation = _get_cart_quotation()
		update_delivery_charges(quotation)
		self.assertEqual(quotation.grand_total, 80 + extra)
		self.assertEqual(len(quotation.taxes), template_copies if colliding else 0)
