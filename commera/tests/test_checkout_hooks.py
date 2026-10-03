# Copyright (c) 2026, company@bwhstudios.com and Contributors

from unittest.mock import patch

import frappe
from bwh_payments.bwh_payments.doctype.gateway_payment_request.test_gateway_payment_request import (
	GATEWAY,
	configure_stripe_gateway,
	remove_stripe_gateway,
)
from bwh_payments.bwh_payments.doctype.stripe_gateway_settings import stripe_gateway_settings
from bwh_payments.currency import to_minor_units
from bwh_payments.tests.fake_stripe import FakeStripeClient
from frappe.deferred_insert import queue_prefix
from frappe.tests import IntegrationTestCase

from commera.api.admin.orders import get_order_charges
from commera.api.checkout import apply_shipping_rule
from commera.api.payments import (
	COD_PAYMENT_MODE,
	CheckoutPriceChangedError,
	confirm_payment,
	generate_quotation_for_cart,
	initiate_checkout_with_mode,
	update_quotation_address,
)
from commera.api.shipping import (
	get_checkout_summary,
	get_order_charge_lines,
	get_shipping_options,
	set_delivery_option,
)
from commera.core import _get_cart_quotation
from commera.tests import test_cart_checkout
from commera.tests.test_admin_orders import ensure_fiscal_year
from commera.tests.test_payment_hooks import patch_app_hooks
from commera.www.cart.checkout import get_context as get_checkout_context

REFUSAL = "Engraved items ship to India only."
GIFT_WRAP = "Gift Wrap"
GIFT_WRAP_FEE = 25.0
# Reads like the store's own delivery row, which get_charge_lines matches on this prefix.
INSURANCE = "Delivery Charges insurance"
HANDLING = "Handling"
HANDLING_SHARE = 0.05
GENERIC_FAILURE = "Something went wrong, please try again."
APP_SECRET = "Printful API key is missing"
EXPRESS = "ZZ Express"
STANDARD = "ZZ Standard"
EXPRESS_LABEL = "Express, gift wrapped"
EXPRESS_REPRICED = 80.0
QUOTED_OPTIONS = [
	{"title": EXPRESS, "amount": 50.0, "description": "", "is_free": False},
	{"title": STANDARD, "amount": 20.0, "description": "", "is_free": False},
]


def refuse_cart(quotation):
	frappe.flags.commera_checkout_hook_calls.append("validate")
	return REFUSAL


def allow_cart(quotation):
	frappe.flags.commera_checkout_hook_calls.append("validate")


def crash_validating_cart(quotation):
	frappe.throw(APP_SECRET)


def charge_gift_wrap(quotation):
	frappe.flags.commera_checkout_hook_calls.append("fees")
	return [{"description": GIFT_WRAP, "amount": GIFT_WRAP_FEE}]


def charge_handling_on_grand_total(quotation):
	return [{"description": HANDLING, "amount": quotation.grand_total * HANDLING_SHARE}]


def charge_test_fee(quotation):
	return [frappe.flags.commera_test_fee]


def crash_charging_fees(quotation):
	frappe.throw(APP_SECRET)


def hide_express(quotation, options):
	return [option for option in options if option["title"] != EXPRESS]


def reprice_express(quotation, options):
	return [
		{**option, "amount": EXPRESS_REPRICED, "label": EXPRESS_LABEL}
		if option["title"] == EXPRESS
		else option
		for option in options
	]


def halve_delivery_amounts(quotation, options):
	return [{**option, "amount": option["amount"] / 2} for option in options]


def add_delivery_option(quotation, options):
	return [*options, {"title": "ZZ Teleport", "amount": 0}]


def rename_delivery_option(quotation, options):
	return [{**options[0], "title": "ZZ Renamed"}, *options[1:]]


def charge_negative_delivery(quotation, options):
	return [{**option, "amount": -1} for option in options]


def crash_listing_delivery_options(quotation, options):
	frappe.throw(APP_SECRET)


def hide_cod(quotation, methods):
	return [method for method in methods if method != COD_PAYMENT_MODE]


def hide_gateway(quotation, methods):
	return [method for method in methods if method != GATEWAY]


def add_payment_method(quotation, methods):
	return [*methods, "ZZ Barter"]


def crash_listing_payment_methods(quotation, methods):
	frappe.throw(APP_SECRET)


class TestCheckoutHooks(IntegrationTestCase):
	create_shopper = test_cart_checkout.TestCartCheckout.create_shopper
	create_item = test_cart_checkout.TestCartCheckout.create_item
	cart_line = test_cart_checkout.TestCartCheckout.cart_line
	address_payload = test_cart_checkout.TestCartCheckout.address_payload
	get_output_tax_account = test_cart_checkout.TestCartCheckout.get_output_tax_account
	add_tax_to_cart = test_cart_checkout.TestCartCheckout.add_tax_to_cart
	set_commera_settings = test_cart_checkout.TestCartCheckout.set_commera_settings
	set_store_pickup = test_cart_checkout.TestCartCheckout.set_store_pickup
	create_pickup_warehouse = test_cart_checkout.TestCartCheckout.create_pickup_warehouse
	create_shop_address = test_cart_checkout.TestCartCheckout.create_shop_address
	pickup_payload = test_cart_checkout.TestCartCheckout.pickup_payload

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.clear_cache()
		commera_settings = frappe.get_cached_doc("Commera Settings")
		cls.default_price_list = commera_settings.get_default_price_list()
		cls.sale_price_list = commera_settings.get_sale_price_list()
		cls.warehouse = commera_settings.ecommerce_warehouse
		configure_stripe_gateway()
		ensure_fiscal_year()

	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		# The gateway fixture runs outside the per-test rollback, so a fake-keyed gateway would stay enabled.
		frappe.db.rollback()
		remove_stripe_gateway()
		frappe.db.commit()

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		FakeStripeClient.reset()
		stripe_client_patch = patch.object(stripe_gateway_settings.stripe, "StripeClient", FakeStripeClient)
		stripe_client_patch.start()
		self.addCleanup(stripe_client_patch.stop)
		frappe.cache.delete_value(f"{queue_prefix}Error Log")
		self.addCleanup(frappe.cache.delete_value, f"{queue_prefix}Error Log")
		frappe.flags.commera_checkout_hook_calls = []
		self.addCleanup(frappe.flags.pop, "commera_checkout_hook_calls", None)

		self.shopper = self.create_shopper()
		self.item = self.create_item(sale_rate=test_cart_checkout.SALE_RATE)
		self.set_commera_settings({"cod_enabled": 1, "cod_charge": 0})

	def open_cart(self, qty: int = 3):
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.item, qty)]})
		update_quotation_address(self.address_payload())
		return _get_cart_quotation()

	def gateway_requests(self, quotation_name: str) -> list:
		return frappe.get_all(
			"Gateway Payment Request",
			filters={"ref_doctype": "Quotation", "ref_docname": quotation_name},
			fields=["name", "amount"],
		)

	def placed_orders(self, quotation_name: str) -> list:
		return frappe.get_all("Sales Order Item", {"prevdoc_docname": quotation_name}, pluck="parent")

	def fee_rows(self, quotation) -> list:
		return [row for row in quotation.taxes if row.commera_app_fee]

	def queued_error_logs(self) -> str:
		return frappe.as_unicode(b"".join(frappe.cache.lrange(f"{queue_prefix}Error Log", 0, -1)))

	def test_an_app_refusal_reaches_the_shopper_and_opens_no_payment(self):
		patch_app_hooks(self, {"commera_validate_cart": [f"{__name__}.refuse_cart"]})
		quotation = self.open_cart()

		with self.assertRaisesRegex(frappe.ValidationError, REFUSAL):
			initiate_checkout_with_mode(GATEWAY)

		frappe.set_user("Administrator")
		self.assertEqual(self.gateway_requests(quotation.name), [])
		self.assertEqual(FakeStripeClient.created_sessions, [])
		self.assertNotIn(REFUSAL, self.queued_error_logs(), "a refusal the shopper can fix is no error")

	def test_an_app_refusal_stops_a_cod_order_at_checkout_and_at_confirmation(self):
		patch_app_hooks(self, {"commera_validate_cart": [f"{__name__}.refuse_cart"]})
		quotation = self.open_cart()

		with self.assertRaisesRegex(frappe.ValidationError, REFUSAL):
			initiate_checkout_with_mode(COD_PAYMENT_MODE)
		with self.assertRaisesRegex(frappe.ValidationError, REFUSAL):
			confirm_payment(quotation.name, payment_mode=COD_PAYMENT_MODE)

		frappe.set_user("Administrator")
		self.assertEqual(self.placed_orders(quotation.name), [])
		self.assertEqual(frappe.db.get_value("Quotation", quotation.name, "docstatus"), 0)

	def test_a_crashing_validator_blocks_checkout_with_a_generic_message_and_is_logged(self):
		handler = f"{__name__}.crash_validating_cart"
		patch_app_hooks(self, {"commera_validate_cart": [handler]})
		quotation = self.open_cart()
		frappe.local.message_log = []

		with self.assertRaisesRegex(frappe.ValidationError, GENERIC_FAILURE):
			initiate_checkout_with_mode(GATEWAY)

		shown_to_shopper = frappe.as_json(frappe.local.message_log)
		self.assertIn(GENERIC_FAILURE, shown_to_shopper)
		self.assertNotIn(APP_SECRET, shown_to_shopper)
		self.assertIn(f"commera_validate_cart hook failed: {handler}", self.queued_error_logs())
		frappe.set_user("Administrator")
		self.assertEqual(self.gateway_requests(quotation.name), [])

	def test_each_checkout_hook_runs_once_per_checkout(self):
		patch_app_hooks(
			self,
			{
				"commera_validate_cart": [f"{__name__}.allow_cart"],
				"commera_cart_fees": [f"{__name__}.charge_gift_wrap"],
			},
		)
		self.open_cart()
		frappe.flags.commera_checkout_hook_calls.clear()

		initiate_checkout_with_mode(GATEWAY)

		self.assertEqual(sorted(frappe.flags.commera_checkout_hook_calls), ["fees", "validate"])

	def test_an_app_fee_is_an_untaxed_charge_the_gateway_bills(self):
		patch_app_hooks(self, {"commera_cart_fees": [f"{__name__}.charge_gift_wrap"]})
		self.open_cart()
		self.add_tax_to_cart()
		quotation = _get_cart_quotation()
		summary = get_checkout_summary(quotation)

		initiate_checkout_with_mode(GATEWAY, expected_total=summary["total"])

		(fee_row,) = self.fee_rows(_get_cart_quotation())
		self.assertEqual(fee_row.charge_type, "Actual")
		self.assertEqual(fee_row.tax_amount, GIFT_WRAP_FEE)
		self.assertEqual(
			fee_row.account_head, frappe.db.get_single_value("Commera Settings", "charge_account_head")
		)
		self.assertEqual(summary["app_fees"], [{"description": GIFT_WRAP, "amount": GIFT_WRAP_FEE}])
		# 18% of the 270 of goods alone: had the fee been in the tax base this would read 53.10.
		self.assertIn({"description": test_cart_checkout.TAX_DESCRIPTION, "amount": 48.6}, summary["taxes"])
		self.assertEqual(summary["total"], round(270 + 48.6 + summary["shipping"] + GIFT_WRAP_FEE))

		frappe.set_user("Administrator")
		(payment_request,) = self.gateway_requests(quotation.name)
		self.assertEqual(payment_request.amount, summary["total"])
		gateway_line = FakeStripeClient.created_sessions[-1]["line_items"][0]["price_data"]
		self.assertEqual(gateway_line["unit_amount"], to_minor_units(summary["total"], quotation.currency))

	def test_a_pickup_cart_keeps_its_app_fee(self):
		patch_app_hooks(self, {"commera_cart_fees": [f"{__name__}.charge_gift_wrap"]})
		self.set_store_pickup(1)
		warehouse = self.create_pickup_warehouse()
		self.open_cart()

		summary = update_quotation_address(self.pickup_payload(warehouse))["checkout_summary"]
		initiate_checkout_with_mode(GATEWAY, expected_total=summary["total"])

		self.assertEqual(summary["app_fees"], [{"description": GIFT_WRAP, "amount": GIFT_WRAP_FEE}])
		self.assertEqual(summary["total"], 270 + GIFT_WRAP_FEE)
		self.assertEqual(len(self.fee_rows(_get_cart_quotation())), 1)

	def test_an_app_fee_carries_into_the_sales_order(self):
		patch_app_hooks(self, {"commera_cart_fees": [f"{__name__}.charge_gift_wrap"]})
		quotation = self.open_cart()

		initiate_checkout_with_mode(COD_PAYMENT_MODE)
		order_name = confirm_payment(quotation.name, payment_mode=COD_PAYMENT_MODE)["order_name"]

		frappe.set_user("Administrator")
		sales_order = frappe.get_doc("Sales Order", order_name)
		self.assertEqual(
			[(row.description, row.tax_amount) for row in self.fee_rows(sales_order)],
			[(GIFT_WRAP, GIFT_WRAP_FEE)],
		)
		self.assertEqual(
			get_order_charge_lines(sales_order.name, sales_order.shipping_rule)["app_fees"],
			[{"description": GIFT_WRAP, "amount": GIFT_WRAP_FEE}],
		)

	def test_a_fee_named_like_delivery_stays_a_fee_and_leaves_the_order_tax_alone(self):
		patch_app_hooks(self, {"commera_cart_fees": [f"{__name__}.charge_test_fee"]})
		self.addCleanup(frappe.flags.pop, "commera_test_fee", None)
		frappe.flags.commera_test_fee = {"description": INSURANCE, "amount": GIFT_WRAP_FEE}
		quotation = self.open_cart()
		self.add_tax_to_cart()

		initiate_checkout_with_mode(COD_PAYMENT_MODE)
		order_name = confirm_payment(quotation.name, payment_mode=COD_PAYMENT_MODE)["order_name"]

		frappe.set_user("Administrator")
		sales_order = frappe.get_doc("Sales Order", order_name)
		charge_lines = get_order_charge_lines(sales_order.name, sales_order.shipping_rule)
		charges = get_order_charges(sales_order)
		self.assertEqual(charge_lines["app_fees"], [{"description": INSURANCE, "amount": GIFT_WRAP_FEE}])
		self.assertEqual(charges["shipping"], charge_lines["shipping"])
		self.assertNotIn(INSURANCE, [line["description"] for line in charge_lines["taxes"]])
		self.assertEqual(charges["tax"], 48.6)

	def test_a_crashing_fee_hook_never_blocks_a_cart_edit_but_blocks_checkout(self):
		handler = f"{__name__}.crash_charging_fees"
		patch_app_hooks(self, {"commera_cart_fees": [handler]})

		quotation = self.open_cart()
		apply_shipping_rule()

		self.assertEqual(self.fee_rows(_get_cart_quotation()), [])
		self.assertIn(f"commera_cart_fees hook failed: {handler}", self.queued_error_logs())
		with self.assertRaisesRegex(frappe.ValidationError, GENERIC_FAILURE):
			initiate_checkout_with_mode(GATEWAY)
		frappe.set_user("Administrator")
		self.assertEqual(self.gateway_requests(quotation.name), [])

	def test_a_fee_hook_failing_after_checkout_opened_blocks_the_cod_confirmation(self):
		patch_app_hooks(self, {"commera_cart_fees": [f"{__name__}.charge_test_fee"]})
		self.addCleanup(frappe.flags.pop, "commera_test_fee", None)
		frappe.flags.commera_test_fee = {"description": GIFT_WRAP, "amount": GIFT_WRAP_FEE}
		quotation = self.open_cart()
		initiate_checkout_with_mode(COD_PAYMENT_MODE)

		frappe.flags.commera_test_fee = {"description": GIFT_WRAP, "amount": -5.0}
		with self.assertRaisesRegex(frappe.ValidationError, GENERIC_FAILURE):
			confirm_payment(quotation.name, payment_mode=COD_PAYMENT_MODE)

		frappe.set_user("Administrator")
		self.assertEqual(self.placed_orders(quotation.name), [])

	def test_recomputing_charges_replaces_the_fee_instead_of_stacking_it(self):
		patch_app_hooks(self, {"commera_cart_fees": [f"{__name__}.charge_handling_on_grand_total"]})
		self.open_cart()
		first_total = _get_cart_quotation().grand_total

		apply_shipping_rule()
		apply_shipping_rule()

		quotation = _get_cart_quotation()
		(fee_row,) = self.fee_rows(quotation)
		self.assertEqual(fee_row.description, HANDLING)
		self.assertEqual(quotation.grand_total, first_total)
		self.assertAlmostEqual(
			fee_row.tax_amount, (quotation.grand_total - fee_row.tax_amount) * HANDLING_SHARE, places=2
		)

	def test_uninstalling_the_fee_app_drops_its_fee_at_the_next_recompute(self):
		patch_app_hooks(self, {"commera_cart_fees": [f"{__name__}.charge_gift_wrap"]})
		self.open_cart()
		self.assertEqual(len(self.fee_rows(_get_cart_quotation())), 1)

		patch_app_hooks(self, {"commera_cart_fees": []})
		apply_shipping_rule()

		self.assertEqual(self.fee_rows(_get_cart_quotation()), [])

	def test_an_invalid_fee_blocks_checkout(self):
		patch_app_hooks(self, {"commera_cart_fees": [f"{__name__}.charge_test_fee"]})
		self.addCleanup(frappe.flags.pop, "commera_test_fee", None)
		frappe.flags.commera_test_fee = {"description": GIFT_WRAP, "amount": GIFT_WRAP_FEE}
		quotation = self.open_cart()

		for invalid_fee in (
			{"description": GIFT_WRAP, "amount": -5.0},
			{"description": GIFT_WRAP, "amount": "25"},
			{"description": " ", "amount": GIFT_WRAP_FEE},
			{"amount": GIFT_WRAP_FEE},
		):
			with self.subTest(fee=invalid_fee):
				frappe.flags.commera_test_fee = invalid_fee
				with self.assertRaisesRegex(frappe.ValidationError, GENERIC_FAILURE):
					initiate_checkout_with_mode(GATEWAY)

		frappe.set_user("Administrator")
		self.assertEqual(self.gateway_requests(quotation.name), [])

	def test_a_zero_fee_is_no_fee_and_checkout_goes_through(self):
		patch_app_hooks(self, {"commera_cart_fees": [f"{__name__}.charge_test_fee"]})
		self.addCleanup(frappe.flags.pop, "commera_test_fee", None)
		frappe.flags.commera_test_fee = {"description": GIFT_WRAP, "amount": 0}
		quotation = self.open_cart()

		initiate_checkout_with_mode(GATEWAY)

		frappe.set_user("Administrator")
		self.assertEqual(self.fee_rows(frappe.get_doc("Quotation", quotation.name)), [])
		self.assertEqual(len(self.gateway_requests(quotation.name)), 1)

	def quote_delivery_options(self):
		quote_patch = patch("commera.api.shipping.get_quoted_options", return_value=QUOTED_OPTIONS)
		quote_patch.start()
		self.addCleanup(quote_patch.stop)

	def open_delivery_cart(self, delivery_option: str = EXPRESS):
		self.quote_delivery_options()
		quotation = self.open_cart()
		set_delivery_option(delivery_option)
		return quotation

	def listed_options(self) -> list[tuple]:
		return [
			(option["title"], option["amount"], option.get("label"))
			for option in get_shipping_options()["options"]
		]

	def test_a_hidden_delivery_option_is_not_listed_cannot_be_chosen_and_is_refused_at_payment(self):
		quotation = self.open_delivery_cart(EXPRESS)
		patch_app_hooks(self, {"commera_delivery_options": [f"{__name__}.hide_express"]})

		self.assertEqual(self.listed_options(), [(STANDARD, 20.0, None)])
		with self.assertRaisesRegex(frappe.ValidationError, "is not available"):
			set_delivery_option(EXPRESS)
		with self.assertRaisesRegex(CheckoutPriceChangedError, "no longer available"):
			initiate_checkout_with_mode(GATEWAY, delivery_option=EXPRESS)

		frappe.set_user("Administrator")
		self.assertEqual(self.gateway_requests(quotation.name), [])

	def test_a_repriced_option_costs_the_same_from_listing_to_order_and_keeps_its_title(self):
		patch_app_hooks(self, {"commera_delivery_options": [f"{__name__}.reprice_express"]})
		quotation = self.open_delivery_cart(EXPRESS)

		self.assertEqual(
			self.listed_options(), [(EXPRESS, EXPRESS_REPRICED, EXPRESS_LABEL), (STANDARD, 20.0, None)]
		)
		self.assertEqual(_get_cart_quotation().custom_delivery_charge, EXPRESS_REPRICED)
		shown_total = get_checkout_summary(_get_cart_quotation())["cash_on_delivery"]["total"]
		initiate_checkout_with_mode(COD_PAYMENT_MODE, delivery_option=EXPRESS, expected_total=shown_total)
		order_name = confirm_payment(quotation.name, payment_mode=COD_PAYMENT_MODE)["order_name"]

		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value(
				"Sales Order", order_name, ["custom_delivery_option", "custom_delivery_charge"], as_dict=True
			),
			{"custom_delivery_option": EXPRESS, "custom_delivery_charge": EXPRESS_REPRICED},
		)

	def test_delivery_hooks_chain_in_hook_order(self):
		self.open_delivery_cart(EXPRESS)
		patch_app_hooks(
			self,
			{
				"commera_delivery_options": [
					f"{__name__}.reprice_express",
					f"{__name__}.halve_delivery_amounts",
				]
			},
		)

		self.assertEqual(
			self.listed_options(), [(EXPRESS, EXPRESS_REPRICED / 2, EXPRESS_LABEL), (STANDARD, 10.0, None)]
		)

	def test_a_failing_delivery_hook_lists_the_quoted_options_but_blocks_payment(self):
		quotation = self.open_delivery_cart(EXPRESS)
		for handler in (
			crash_listing_delivery_options,
			add_delivery_option,
			rename_delivery_option,
			charge_negative_delivery,
		):
			with self.subTest(handler=handler.__name__):
				handler_path = f"{__name__}.{handler.__name__}"
				patch_app_hooks(self, {"commera_delivery_options": [handler_path]})

				self.assertEqual(self.listed_options(), [(EXPRESS, 50.0, None), (STANDARD, 20.0, None)])
				self.assertIn(
					f"commera_delivery_options hook failed: {handler_path}", self.queued_error_logs()
				)
				with self.assertRaisesRegex(frappe.ValidationError, GENERIC_FAILURE):
					initiate_checkout_with_mode(GATEWAY, delivery_option=EXPRESS)

		frappe.set_user("Administrator")
		self.assertEqual(self.gateway_requests(quotation.name), [])

	def render_payment_methods(self) -> tuple[bool, int]:
		context = frappe._dict()
		get_checkout_context(context)
		return GATEWAY in context.payment_gateways, context.show_cod

	def test_a_hidden_gateway_is_left_off_the_checkout_page_and_refused_at_payment(self):
		quotation = self.open_cart()
		self.assertEqual(self.render_payment_methods(), (True, 1))
		patch_app_hooks(self, {"commera_payment_methods": [f"{__name__}.hide_gateway"]})

		self.assertEqual(self.render_payment_methods(), (False, 1))
		with self.assertRaisesRegex(frappe.ValidationError, "not available for your order"):
			initiate_checkout_with_mode(GATEWAY)

		frappe.set_user("Administrator")
		self.assertEqual(self.gateway_requests(quotation.name), [])
		self.assertEqual(FakeStripeClient.created_sessions, [])

	def test_hidden_cash_on_delivery_is_refused_at_checkout_and_at_confirmation(self):
		patch_app_hooks(self, {"commera_payment_methods": [f"{__name__}.hide_cod"]})
		quotation = self.open_cart()

		self.assertEqual(self.render_payment_methods(), (True, 0))
		with self.assertRaisesRegex(frappe.ValidationError, "Cash on delivery is not available"):
			initiate_checkout_with_mode(COD_PAYMENT_MODE)
		with self.assertRaisesRegex(frappe.ValidationError, "Cash on delivery is not available"):
			confirm_payment(quotation.name, payment_mode=COD_PAYMENT_MODE)

		frappe.set_user("Administrator")
		self.assertEqual(self.placed_orders(quotation.name), [])

	def test_a_failing_payment_method_hook_shows_every_method_but_blocks_checkout(self):
		quotation = self.open_cart()
		for handler in (crash_listing_payment_methods, add_payment_method):
			with self.subTest(handler=handler.__name__):
				handler_path = f"{__name__}.{handler.__name__}"
				patch_app_hooks(self, {"commera_payment_methods": [handler_path]})

				self.assertEqual(self.render_payment_methods(), (True, 1))
				self.assertIn(
					f"commera_payment_methods hook failed: {handler_path}", self.queued_error_logs()
				)
				with self.assertRaisesRegex(frappe.ValidationError, GENERIC_FAILURE):
					initiate_checkout_with_mode(GATEWAY)

		frappe.set_user("Administrator")
		self.assertEqual(self.gateway_requests(quotation.name), [])
