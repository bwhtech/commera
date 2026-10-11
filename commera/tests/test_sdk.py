# Copyright (c) 2026, company@bwhstudios.com and Contributors

import importlib

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.tests import IntegrationTestCase

from commera.api.shipping import is_connector_installed
from commera.checkout_hooks import PLUGIN_FEE_FIELD
from commera.plugin_events import PLUGINS_USER, get_order_snapshot
from commera.sdk import STORE_ORDER_TYPE, as_plugin_user, cart, catalog, orders
from commera.sdk.types import (
	Address,
	Cart,
	CartLine,
	CatalogItem,
	Charge,
	ChargeSummary,
	CheckoutSummary,
	Order,
	OrderLine,
	Stage,
)
from commera.tests import test_cart_checkout, test_checkout_hooks, test_plugin_events
from commera.tests.test_admin_orders import ensure_fiscal_year, get_company_account, make_test_sales_order
from commera.tests.test_payment_hooks import patch_app_hooks
from commera.utils import update_sales_order_ecommerce_status

# Removing or renaming a name here breaks apps built on the SDK, so it needs an API_VERSION bump.
PUBLIC_NAMES = {
	"commera.sdk": ["API_VERSION", "STORE_ORDER_TYPE", "as_plugin_user", "cart", "catalog", "orders"],
	"commera.sdk.cart": ["get_cart", "set_cart_fields"],
	"commera.sdk.catalog": ["get_items"],
	"commera.sdk.orders": ["ShippingNotInstalled", "get_order", "get_orders", "record_shipment"],
	"commera.sdk.types": [
		"Address",
		"Cart",
		"CartLine",
		"CatalogItem",
		"Charge",
		"ChargeSummary",
		"CheckoutSummary",
		"Order",
		"OrderLine",
		"Stage",
	],
}
APP = "bwh_payments"
APP_FIELD = f"{APP}_zz_sdk_note"
FEE_DESCRIPTION = "ZZ SDK wrap"
FEE_AMOUNT = 25.0


def charge_note_fee(quotation):
	if not quotation.get(APP_FIELD):
		return []
	return [{"description": FEE_DESCRIPTION, "amount": FEE_AMOUNT, "account_head": get_company_account()}]


class TestSdk(IntegrationTestCase):
	create_shopper = test_cart_checkout.TestCartCheckout.create_shopper
	create_item = test_cart_checkout.TestCartCheckout.create_item
	cart_line = test_cart_checkout.TestCartCheckout.cart_line
	address_payload = test_cart_checkout.TestCartCheckout.address_payload
	open_cart = test_checkout_hooks.TestCheckoutHooks.open_cart
	list_item = test_plugin_events.TestPluginEvents.list_item

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# A real column, so the app field saves; the DDL commits, so it cannot live inside a test.
		create_custom_fields(
			{
				doctype: [{"fieldname": APP_FIELD, "fieldtype": "Data", "label": "ZZ SDK Note"}]
				for doctype in ("Quotation", "Sales Order")
			},
			ignore_validate=True,
		)
		frappe.db.commit()
		commera_settings = frappe.get_cached_doc("Commera Settings")
		cls.default_price_list = commera_settings.get_default_price_list()
		cls.sale_price_list = commera_settings.get_sale_price_list()
		cls.warehouse = commera_settings.ecommerce_warehouse
		ensure_fiscal_year()

	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		frappe.db.rollback()
		for doctype in ("Quotation", "Sales Order"):
			frappe.delete_doc("Custom Field", f"{doctype}-{APP_FIELD}", ignore_missing=True, force=True)
		frappe.db.commit()

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		patch_app_hooks(self, {"commera_hooks": {"cart_fees": [f"{__name__}.charge_note_fee"]}})
		test_plugin_events.patch_app_declarations(
			self, {APP: {"commera_events": {"order_paid": [f"{APP}.paid"]}}}
		)
		self.shopper = self.create_shopper()
		self.item = self.create_item(sale_rate=test_cart_checkout.SALE_RATE)

	def make_store_order(self, submit: bool = True):
		sales_order = make_test_sales_order(order_type=STORE_ORDER_TYPE, submit=False)
		sales_order.append(
			"taxes",
			{
				"description": FEE_DESCRIPTION,
				"charge_type": "Actual",
				"account_head": get_company_account(),
				"tax_amount": FEE_AMOUNT,
				"included_in_print_rate": 0,
				PLUGIN_FEE_FIELD: 1,
			},
		)
		sales_order.set(APP_FIELD, "Happy birthday")
		sales_order.save()
		if submit:
			sales_order.submit()
		return sales_order

	def assert_shape(self, result: dict, shape):
		self.assertEqual(set(result), shape.__required_keys__ | shape.__optional_keys__)

	def test_the_public_names_are_frozen(self):
		for module_name, names in PUBLIC_NAMES.items():
			module = importlib.import_module(module_name)
			with self.subTest(module_name):
				self.assertEqual(sorted(module.__all__), sorted(names))
				self.assertTrue(all(hasattr(module, name) for name in names))

	def test_every_result_has_exactly_its_declared_keys(self):
		order = orders.get_order(self.make_store_order().name)
		self.assert_shape(order, Order)
		self.assert_shape(order["items"][0], OrderLine)
		self.assert_shape(order["stage"], Stage)
		self.assert_shape(order["plugin_fees"][0], Charge)

		self.assert_shape(catalog.get_items([self.item])[self.item], CatalogItem)

		self.open_cart()
		current_cart = cart.get_cart()
		self.assert_shape(current_cart, Cart)
		self.assert_shape(current_cart["items"][0], CartLine)
		summary = cart.set_cart_fields({APP_FIELD: "Wrap it"})
		self.assert_shape(summary, CheckoutSummary)
		self.assert_shape(summary["cash_on_delivery"], ChargeSummary)
		self.assert_shape(summary["plugin_fees"][0], Charge)

	def test_an_order_reads_its_plugin_fee_its_stage_and_the_app_field_asked_for(self):
		sales_order = self.make_store_order()

		order = orders.get_order(sales_order.name, extra_fields=[APP_FIELD])

		self.assertEqual(order["order_type"], STORE_ORDER_TYPE)
		self.assertEqual(order["plugin_fees"], [{"description": FEE_DESCRIPTION, "amount": FEE_AMOUNT}])
		self.assertEqual(order["grand_total"], sales_order.grand_total)
		self.assertEqual(order["stage"]["key"], "to_fulfil")
		self.assertFalse(order["is_cancelled"])
		self.assertFalse(order["is_paid"])
		self.assertEqual(order["plugin_fields"], {APP_FIELD: "Happy birthday"})
		self.assertEqual(
			[(line["line_id"], line["qty"]) for line in order["items"]],
			[(row.name, row.qty) for row in sales_order.items],
		)

	def test_a_cancelled_order_and_one_placed_outside_the_store_read_as_such(self):
		cancelled = self.make_store_order()
		cancelled.cancel()
		desk_order = make_test_sales_order(order_type="Sales")

		order = orders.get_order(cancelled.name)
		self.assertTrue(order["is_cancelled"])
		self.assertEqual(order["stage"]["key"], "cancelled")
		self.assertEqual(orders.get_order(desk_order.name)["order_type"], "Sales")

	def test_an_order_and_its_event_ship_to_the_shipping_address_else_the_billing_one(self):
		billing = self.make_address("Billing", "Pune")
		shipping = self.make_address("Shipping", "Mumbai")
		shipped = self.make_store_order()
		frappe.db.set_value(
			"Sales Order", shipped.name, {"customer_address": billing, "shipping_address_name": shipping}
		)
		billed_only = self.make_store_order()
		frappe.db.set_value(
			"Sales Order", billed_only.name, {"customer_address": billing, "shipping_address_name": ""}
		)
		no_address = self.make_store_order()

		order = orders.get_order(shipped.name)
		self.assert_shape(order["shipping_address"], Address)
		self.assertEqual(
			(order["shipping_address"]["name"], order["shipping_address"]["city"]), (shipping, "Mumbai")
		)
		self.assertEqual(get_order_snapshot(shipped.name)["shipping_address"], order["shipping_address"])
		self.assertEqual(orders.get_order(billed_only.name)["shipping_address"]["name"], billing)
		self.assertEqual(get_order_snapshot(billed_only.name)["shipping_address"]["city"], "Pune")
		self.assertIsNone(orders.get_order(no_address.name)["shipping_address"])
		self.assertIsNone(get_order_snapshot(no_address.name)["shipping_address"])

	def make_address(self, address_type: str, city: str) -> str:
		address = frappe.new_doc("Address")
		address.update(
			{
				"address_title": f"ZZ SDK {city}",
				"address_type": address_type,
				"address_line1": "1 Test Street",
				"city": city,
				"state": "Maharashtra",
				"pincode": "400001",
				"country": "India",
				"phone": "9999999999",
			}
		)
		address.insert(ignore_permissions=True)
		return address.name

	def test_a_field_no_installed_app_owns_is_refused(self):
		sales_order = self.make_store_order(submit=False)

		with self.assertRaises(frappe.ValidationError):
			orders.get_order(sales_order.name, extra_fields=["grand_total"])
		self.open_cart()
		with self.assertRaises(frappe.ValidationError):
			cart.set_cart_fields({"grand_total": 1})

	def test_a_user_without_read_access_is_refused_until_the_plugin_acts_as_the_plugin_user(self):
		sales_order = self.make_store_order()
		frappe.set_user(self.shopper)

		with self.assertRaises(frappe.PermissionError):
			orders.get_order(sales_order.name)
		with self.assertRaises(frappe.PermissionError):
			orders.get_orders([sales_order.name])
		with as_plugin_user("commera"):
			self.assertEqual(frappe.session.user, PLUGINS_USER)
			self.assertEqual(orders.get_order(sales_order.name)["name"], sales_order.name)
		self.assertEqual(frappe.session.user, self.shopper)
		with self.assertRaises(frappe.ValidationError):
			with as_plugin_user("zz_not_installed"):
				pass

	def test_a_page_of_orders_costs_no_more_queries_than_one_order(self):
		order_names = [self.make_store_order().name for _ in range(3)]
		orders.get_orders(order_names[:1])

		with self.assertQueryCount(14):
			page = orders.get_orders([*order_names, "ZZ-NO-SUCH-ORDER"])

		self.assertEqual(sorted(page), sorted(order_names))
		self.assertTrue(all(order["plugin_fees"] for order in page.values()))

	def test_items_read_their_shopper_price_store_stock_and_listing(self):
		listed_item = self.list_item(self.item)
		unlisted_item = self.create_item(sale_rate=None)

		items = catalog.get_items([listed_item, unlisted_item, "ZZ-NO-SUCH-ITEM"])

		self.assertEqual(sorted(items), sorted([listed_item, unlisted_item]))
		self.assertTrue(items[listed_item]["is_listed"])
		self.assertEqual(items[listed_item]["price"], test_cart_checkout.SALE_RATE)
		self.assertEqual(items[listed_item]["list_price"], test_cart_checkout.DEFAULT_RATE)
		self.assertEqual(items[listed_item]["available_qty"], test_cart_checkout.IN_STOCK_QTY)
		self.assertFalse(items[unlisted_item]["is_listed"])
		self.assertEqual(items[unlisted_item]["price"], test_cart_checkout.DEFAULT_RATE)

	def test_a_drop_shipped_item_reads_as_unlimited_whatever_its_stock(self):
		drop_shipped_item = self.create_item(sale_rate=None, stock_qty=0, delivered_by_supplier=1)

		items = catalog.get_items([self.item, drop_shipped_item])

		self.assertTrue(items[drop_shipped_item]["unlimited"])
		self.assertFalse(items[self.item]["unlimited"])

	def test_items_read_no_price_and_no_stock_before_the_store_is_set_up(self):
		store_setup = {"ecommerce_warehouse": None, "default_price_list": None, "sale_price_list": None}
		# The rollback is per class, not per test, so the store's setup has to be put back by hand.
		self.addCleanup(frappe.clear_document_cache, "Commera Settings", "Commera Settings")
		self.addCleanup(
			frappe.db.set_single_value,
			"Commera Settings",
			frappe.db.get_value("Commera Settings", None, list(store_setup), as_dict=True),
		)
		frappe.db.set_single_value("Commera Settings", store_setup)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

		item = catalog.get_items([self.item])[self.item]

		self.assertIsNone(item["price"])
		self.assertIsNone(item["list_price"])
		self.assertEqual(item["available_qty"], 0)

	def test_an_app_field_saved_on_the_cart_reprices_the_plugin_fee(self):
		frappe.set_user(self.shopper)
		self.assertIsNone(cart.get_cart())
		quotation = self.open_cart()
		self.assertIsNone(cart.get_cart()["plugin_fields"][APP_FIELD])

		summary = cart.set_cart_fields({APP_FIELD: "Wrap it"})

		self.assertEqual(summary["plugin_fees"], [{"description": FEE_DESCRIPTION, "amount": FEE_AMOUNT}])
		self.assertEqual(frappe.db.get_value("Quotation", quotation.name, APP_FIELD), "Wrap it")
		self.assertEqual(cart.get_cart()["plugin_fields"][APP_FIELD], "Wrap it")

	def test_a_cart_already_paid_for_is_refused(self):
		quotation = self.open_cart()
		frappe.get_doc(
			{
				"doctype": "Gateway Payment Request",
				"name": frappe.generate_hash(length=10),
				"ref_doctype": "Quotation",
				"ref_docname": quotation.name,
				"status": "Paid",
			}
		).db_insert()

		with self.assertRaises(frappe.ValidationError):
			cart.set_cart_fields({APP_FIELD: "Wrap it"})
		self.assertIsNone(frappe.db.get_value("Quotation", quotation.name, APP_FIELD))

	def test_a_recorded_shipment_ships_then_delivers_the_order_and_never_goes_back(self):
		if not is_connector_installed():
			self.skipTest("bwh_shipping is not installed")
		from bwh_shipping.tests.test_carrier_import import create_test_address, create_test_provider_profile

		patch_app_hooks(self, {"commera_events": {"order_fulfilled": [], "order_delivered": []}})
		sales_order = make_test_sales_order(order_type=STORE_ORDER_TYPE)
		sales_order.db_set(
			{
				"shipping_address_name": create_test_address("India"),
				"company_address": create_test_address("India"),
			}
		)
		provider = create_test_provider_profile()
		scan = {"timestamp": "2026-10-01 10:00:00", "status": "In Transit", "event_id": "zz-sdk-scan-1"}

		shipment = orders.record_shipment(
			sales_order.name, provider=provider, awb="ZZ-SDK-AWB", events=[scan]
		)
		self.assertEqual(
			orders.record_shipment(sales_order.name, provider=provider, awb="ZZ-SDK-AWB", events=[scan]),
			shipment,
		)
		self.assertEqual(len(frappe.get_doc("Shipping Request", shipment).tracking_events), 1)
		update_sales_order_ecommerce_status(sales_order.name)
		self.assertEqual(
			frappe.db.get_value("Sales Order", sales_order.name, "custom_ecommerce_status"), "Shipped"
		)
		self.assertTrue(
			frappe.db.exists(
				"Commera Event", {"reference_name": sales_order.name, "event": "order_fulfilled"}
			)
		)

		orders.record_shipment(sales_order.name, provider=provider, awb="ZZ-SDK-AWB", status="Delivered")
		orders.record_shipment(sales_order.name, provider=provider, awb="ZZ-SDK-AWB", status="In Transit")

		self.assertEqual(frappe.db.get_value("Shipping Request", shipment, "status"), "Delivered")
		self.assertEqual(orders.get_order(sales_order.name)["stage"]["key"], "delivered")
		with self.assertRaises(frappe.ValidationError):
			orders.record_shipment(sales_order.name, provider=provider, awb="ZZ-SDK-AWB", status="Teleported")

	def test_a_carrier_named_after_the_first_record_is_saved(self):
		if not is_connector_installed():
			self.skipTest("bwh_shipping is not installed")
		from bwh_shipping.tests.test_carrier_import import create_test_address

		patch_app_hooks(self, {"commera_events": {"order_fulfilled": [], "order_delivered": []}})
		sales_order = make_test_sales_order(order_type=STORE_ORDER_TYPE)
		sales_order.db_set({"shipping_address_name": create_test_address("India"), "company_address": None})

		shipment = orders.record_shipment(sales_order.name, awb="ZZ-LATE-CARRIER-AWB")
		orders.record_shipment(sales_order.name, awb="ZZ-LATE-CARRIER-AWB", carrier="Delhivery")
		orders.record_shipment(sales_order.name, awb="ZZ-LATE-CARRIER-AWB")

		self.assertEqual(frappe.db.get_value("Shipping Request", shipment, "carrier"), "Delhivery")

	def test_a_partner_shipment_needs_no_provider_and_shows_the_shopper_its_link(self):
		if not is_connector_installed():
			self.skipTest("bwh_shipping is not installed")
		from bwh_shipping.tests.test_carrier_import import create_test_address

		from commera.api.shipping import get_order_tracking

		patch_app_hooks(self, {"commera_events": {"order_fulfilled": [], "order_delivered": []}})
		sales_order = make_test_sales_order(order_type=STORE_ORDER_TYPE)
		sales_order.db_set({"shipping_address_name": create_test_address("India"), "company_address": None})
		tracking_url = "https://track.example.com/ZZ-PARTNER-AWB"

		shipment = orders.record_shipment(
			sales_order.name, awb="ZZ-PARTNER-AWB", carrier="Delhivery", tracking_url=tracking_url
		)
		self.assertFalse(
			any(frappe.db.get_value("Shipping Request", shipment, ["provider", "origin_address"]))
		)
		update_sales_order_ecommerce_status(sales_order.name)
		self.assertEqual(
			frappe.db.get_value("Sales Order", sales_order.name, "custom_ecommerce_status"), "Shipped"
		)

		orders.record_shipment(sales_order.name, awb="ZZ-PARTNER-AWB", status="Delivered")
		orders.record_shipment(sales_order.name, awb="ZZ-PARTNER-AWB", status="In Transit")
		update_sales_order_ecommerce_status(sales_order.name)
		self.assertEqual(
			frappe.db.get_value("Sales Order", sales_order.name, "custom_ecommerce_status"), "Delivered"
		)
		self.assertTrue(
			frappe.db.exists(
				"Commera Event", {"reference_name": sales_order.name, "event": "order_delivered"}
			)
		)

		tracking = get_order_tracking(sales_order.name)
		self.assertEqual(
			(tracking["awb"], tracking["carrier"], tracking["status"], tracking["tracking_url"]),
			("ZZ-PARTNER-AWB", "Delhivery", "Delivered", tracking_url),
		)
		with self.assertRaises(frappe.ValidationError):
			orders.record_shipment(
				sales_order.name, awb="ZZ-PARTNER-AWB-2", tracking_url="javascript:alert(1)"
			)
