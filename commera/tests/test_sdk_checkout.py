from unittest.mock import patch

import frappe
from frappe.auth import CookieManager
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.api.payments import COD_PAYMENT_MODE, CheckoutPriceChangedError
from commera.api.storefront import checkout as checkout_api
from commera.core import _get_cart_quotation
from commera.guest import CART_TOKEN_HEADER
from commera.sdk import cart as cart_sdk
from commera.sdk import checkout
from commera.sdk.types import (
	CheckoutResult,
	CheckoutState,
	PaymentMethod,
	PaymentSession,
	PlacedOrder,
	ShippingOption,
	ShippingOptions,
)
from commera.tests import test_cart_checkout, test_plugin_events
from commera.tests.test_admin_orders import ensure_fiscal_year

BILLING_ADDRESS = {
	"first_name": "ZZ",
	"last_name": "Shopper",
	"address_line1": "1 Billing Street",
	"city": "Riyadh",
	"country": test_cart_checkout.COUNTRY,
	"phone": "+966500000001",
}
SHIPPING_ADDRESS = {**BILLING_ADDRESS, "address_line1": "2 Shipping Street"}
GATEWAY_REQUEST_CLASS = (
	"bwh_payments.bwh_payments.doctype.gateway_payment_request.gateway_payment_request.GatewayPaymentRequest"
)


class TestSdkCheckout(IntegrationTestCase):
	create_shopper = test_cart_checkout.TestCartCheckout.create_shopper
	create_item = test_cart_checkout.TestCartCheckout.create_item
	set_commera_settings = test_cart_checkout.TestCartCheckout.set_commera_settings
	set_store_pickup = test_cart_checkout.TestCartCheckout.set_store_pickup
	create_pickup_warehouse = test_cart_checkout.TestCartCheckout.create_pickup_warehouse
	create_shop_address = test_cart_checkout.TestCartCheckout.create_shop_address
	create_payment_request = test_cart_checkout.TestCartCheckout.create_payment_request
	quote_express = test_cart_checkout.TestCartCheckout.quote_express
	list_item = test_plugin_events.TestPluginEvents.list_item

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		commera_settings = frappe.get_cached_doc("Commera Settings")
		cls.default_price_list = commera_settings.get_default_price_list()
		cls.sale_price_list = commera_settings.get_sale_price_list()
		cls.warehouse = commera_settings.ecommerce_warehouse
		ensure_fiscal_year()

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.cache.delete_keys("rl:*127.0.0.1*")
		self.shopper = self.create_shopper()
		self.item = self.create_item(sale_rate=test_cart_checkout.SALE_RATE)
		self.list_item(self.item)

	def fill_cart(self, user: str | None = None, qty: int = 1):
		frappe.set_user(user or self.shopper)
		cart_sdk.add_lines([{"item_code": self.item, "qty": qty}])

	def send_cart_token(self, token: str):
		if not hasattr(frappe.local, "request"):
			self.addCleanup(delattr, frappe.local, "request")
		frappe.local.request = Request(
			EnvironBuilder(
				path="/api/method/commera.api.storefront.checkout.set_addresses",
				headers={CART_TOKEN_HEADER: token},
			).get_environ()
		)
		frappe.local.request_ip = "127.0.0.1"
		frappe.local.cookie_manager = CookieManager()
		frappe.set_user("Guest")

	def allow_guest_checkout(self, allow: int = 1):
		frappe.db.set_single_value("Commera Settings", "allow_guest_checkout", allow)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")
		self.addCleanup(frappe.clear_document_cache, "Commera Settings", "Commera Settings")

	def assert_shape(self, result: dict, shape):
		self.assertEqual(set(result), shape.__required_keys__ | shape.__optional_keys__)

	def test_a_shopper_books_their_cart_to_a_new_address(self):
		self.fill_cart(qty=2)

		state = checkout_api.set_addresses(frappe.as_json(BILLING_ADDRESS))

		self.assert_shape(state, CheckoutState)
		quotation = _get_cart_quotation()
		self.assertEqual(state["cart"], quotation.name)
		self.assertEqual([(row.item_code, row.qty) for row in quotation.items], [(self.item, 2)])
		self.assertEqual(state["billing_address"], state["shipping_address"])
		self.assertEqual(state["billing_address"]["address_line1"], "1 Billing Street")
		self.assertEqual(
			frappe.db.get_value("Dynamic Link", {"parent": quotation.customer_address}, "link_name"),
			quotation.party_name,
		)
		self.assertEqual(state["summary"]["items_total"], 2 * test_cart_checkout.SALE_RATE)

	def test_a_shopper_ships_to_a_saved_address(self):
		self.fill_cart()
		saved_address = checkout.set_addresses(SHIPPING_ADDRESS)["billing_address"]["name"]

		state = checkout.set_addresses(BILLING_ADDRESS, saved_address)

		self.assertEqual(state["shipping_address"]["name"], saved_address)
		self.assertEqual(state["billing_address"]["address_line1"], "1 Billing Street")

	def test_another_shoppers_address_is_refused(self):
		self.fill_cart()
		saved_address = checkout.set_addresses(BILLING_ADDRESS)["billing_address"]["name"]
		frappe.set_user("Administrator")
		other_shopper = self.create_shopper()
		self.fill_cart(other_shopper)

		with self.assertRaises(frappe.DoesNotExistError):
			checkout.set_addresses(saved_address)

	def test_a_guest_books_their_cart_to_the_email_they_typed(self):
		self.allow_guest_checkout()
		self.send_cart_token(frappe.generate_hash(length=32))
		cart_sdk.add_lines([{"item_code": self.item, "qty": 1}])

		state = checkout.set_addresses(BILLING_ADDRESS, email="zz-guest@example.com")

		self.assertEqual(state["email"], "zz-guest@example.com")
		self.assertTrue(frappe.db.get_value("Quotation", state["cart"], "custom_guest_cart_key"))

	def test_a_guest_must_type_an_email_and_cannot_use_a_saved_address(self):
		self.allow_guest_checkout()
		self.send_cart_token(frappe.generate_hash(length=32))
		cart_sdk.add_lines([{"item_code": self.item, "qty": 1}])

		with self.assertRaises(frappe.ValidationError):
			checkout.set_addresses(BILLING_ADDRESS)
		state = checkout.set_addresses(BILLING_ADDRESS, email="zz-guest@example.com")
		with self.assertRaises(frappe.PermissionError):
			checkout.set_addresses(state["billing_address"]["name"], email="zz-guest@example.com")

	def test_a_guest_is_refused_while_guest_checkout_is_off(self):
		self.allow_guest_checkout(0)
		self.send_cart_token(frappe.generate_hash(length=32))

		for call in (
			lambda: checkout.set_addresses(BILLING_ADDRESS, email="zz-guest@example.com"),
			checkout.list_payment_methods,
		):
			with self.subTest(call=call), self.assertRaises(frappe.PermissionError):
				call()

	def test_a_shopper_picks_up_in_store(self):
		self.set_store_pickup(1)
		warehouse = self.create_pickup_warehouse()
		self.fill_cart()

		state = checkout_api.set_store_pickup(warehouse)

		self.assertTrue(state["is_store_pickup"])
		self.assertEqual(state["store"], warehouse)
		self.assertEqual(checkout.list_shipping_options()["reason"], "store_pickup")

	def test_pickup_is_refused_while_store_pickup_is_off(self):
		self.set_store_pickup(0)
		warehouse = self.create_pickup_warehouse()
		self.fill_cart()

		with self.assertRaisesRegex(frappe.ValidationError, "Store pickup is not available"):
			checkout.set_store_pickup(warehouse)

	def test_options_wait_for_an_address(self):
		self.fill_cart()

		self.assertEqual(
			checkout.list_shipping_options(), {"options": [], "selected": None, "reason": "address_missing"}
		)

	def test_a_shopper_picks_a_delivery_option_priced_on_the_server(self):
		self.fill_cart()
		checkout.set_addresses(BILLING_ADDRESS)

		with self.quote_express(50.0):
			options = checkout_api.list_shipping_options()
			state = checkout_api.set_shipping_option("ZZ Express")

		self.assert_shape(options, ShippingOptions)
		self.assert_shape(options["options"][0], ShippingOption)
		self.assertEqual((options["options"][0]["id"], options["options"][0]["amount"]), ("ZZ Express", 50.0))
		self.assertEqual(state["shipping_option"], "ZZ Express")
		self.assertEqual(state["summary"]["shipping"], 50.0)

	def test_an_option_the_cart_was_not_quoted_is_refused(self):
		self.fill_cart()
		checkout.set_addresses(BILLING_ADDRESS)

		with (
			self.quote_express(),
			self.assertRaisesRegex(frappe.ValidationError, "is not available"),
		):
			checkout.set_shipping_option("ZZ Teleport")

	def test_picking_an_option_brings_a_changed_cart_into_checkout(self):
		self.fill_cart()
		checkout.set_addresses(BILLING_ADDRESS)
		cart_sdk.add_lines([{"item_code": self.item, "qty": 2}])

		with self.quote_express():
			checkout.set_shipping_option("ZZ Express")

		self.assertEqual([row.qty for row in _get_cart_quotation().items], [3])

	def test_cash_on_delivery_is_listed_last(self):
		self.set_commera_settings({"cod_enabled": 1, "cod_charge": 0})
		self.fill_cart()

		methods = checkout_api.list_payment_methods()

		self.assert_shape(methods[-1], PaymentMethod)
		self.assertEqual(
			methods[-1], {"id": COD_PAYMENT_MODE, "title": "Cash on Delivery", "is_cash_on_delivery": True}
		)

	def test_a_cash_on_delivery_order_is_placed_on_complete_and_owned_by_the_shopper(self):
		self.set_commera_settings({"cod_enabled": 1, "cod_charge": 0})
		self.fill_cart()
		state = checkout.set_addresses(BILLING_ADDRESS)

		session = checkout_api.start_payment(COD_PAYMENT_MODE, state["summary"]["cash_on_delivery"]["total"])
		self.assertFalse(frappe.db.exists("Sales Order Item", {"prevdoc_docname": session["reference_id"]}))
		result = checkout_api.complete(session["reference_id"])

		self.assert_shape(session, PaymentSession)
		self.assertIn("/account/orders/confirmation", session["redirect_url"])
		self.assert_shape(result, CheckoutResult)
		self.assert_shape(result["order"], PlacedOrder)
		self.assertEqual(result["status"], "Paid")
		self.assertEqual(frappe.db.get_value("Sales Order", result["order"]["name"], "owner"), self.shopper)

	def test_a_total_the_shopper_was_not_shown_is_refused(self):
		self.set_commera_settings({"cod_enabled": 1, "cod_charge": 0})
		self.fill_cart()
		checkout.set_addresses(BILLING_ADDRESS)

		with self.assertRaises(CheckoutPriceChangedError):
			checkout.start_payment(COD_PAYMENT_MODE, expected_total=1)

	def test_payment_is_refused_for_a_cart_changed_since_checkout_began(self):
		self.set_commera_settings({"cod_enabled": 1, "cod_charge": 0})
		self.fill_cart()
		checkout.set_addresses(BILLING_ADDRESS)
		cart_sdk.add_lines([{"item_code": self.item, "qty": 1}])

		with self.assertRaises(CheckoutPriceChangedError):
			checkout.start_payment(COD_PAYMENT_MODE)

	def test_complete_never_places_cash_on_delivery_that_was_not_started(self):
		self.set_commera_settings({"cod_enabled": 1, "cod_charge": 0})
		self.fill_cart()
		checkout.set_addresses(BILLING_ADDRESS)

		with self.assertRaisesRegex(frappe.ValidationError, "No payment record"):
			checkout.complete()
		self.assertFalse(
			frappe.db.exists("Sales Order Item", {"prevdoc_docname": _get_cart_quotation().name})
		)

	def test_complete_reports_a_gateway_payment_still_pending(self):
		self.fill_cart()
		cart_name = checkout.set_addresses(BILLING_ADDRESS)["cart"]
		self.create_payment_request(cart_name, "Pending")

		with patch(f"{GATEWAY_REQUEST_CLASS}.sync_status") as sync_status:
			result = checkout.complete()

		sync_status.assert_called_once()
		self.assertEqual(result, {"status": "Pending", "order": None})

	def test_a_cart_with_a_payment_under_way_cannot_change(self):
		self.fill_cart()
		cart_name = checkout.set_addresses(BILLING_ADDRESS)["cart"]
		self.create_payment_request(cart_name, "Pending")

		with (
			patch(f"{GATEWAY_REQUEST_CLASS}.release_if_unpaid", return_value=False),
			self.assertRaisesRegex(frappe.ValidationError, "already in progress"),
		):
			checkout.set_addresses(SHIPPING_ADDRESS)

	def test_another_shoppers_payment_cannot_be_completed(self):
		self.set_commera_settings({"cod_enabled": 1, "cod_charge": 0})
		self.fill_cart()
		checkout.set_addresses(BILLING_ADDRESS)
		reference_id = checkout.start_payment(COD_PAYMENT_MODE)["reference_id"]
		frappe.set_user("Administrator")
		other_shopper = self.create_shopper()
		frappe.set_user(other_shopper)

		with self.assertRaises(frappe.PermissionError):
			checkout.complete(reference_id)
