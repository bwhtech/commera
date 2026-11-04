from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin.orders import fulfil_order
from commera.api.storefront import orders
from commera.order_access import set_order_access_key
from commera.sdk.types import ReturnOptions, ShopperOrderDetail
from commera.tests.test_admin_orders import make_test_sales_order
from commera.tests.test_order_access import make_website_user

try:
	from erpnext.selling.doctype.sales_order.mapper import make_sales_invoice
except ImportError:
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice


class TestStorefrontOrders(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(frappe.clear_document_cache, "Commera Settings", "Commera Settings")
		self.addCleanup(frappe.db.rollback)
		self.shopper = make_website_user()
		self.other = make_website_user()
		self.sales_order = make_test_sales_order()
		self.sales_order.db_set({"owner": self.shopper, "custom_ecommerce_payment_mode": "COD"})

	def test_a_shopper_cancels_their_own_order(self):
		frappe.set_user(self.shopper)

		order = orders.cancel_order(self.sales_order.name)

		self.assertEqual(
			set(order), ShopperOrderDetail.__required_keys__ | ShopperOrderDetail.__optional_keys__
		)
		self.assertTrue(order["is_cancelled"])

	def test_only_the_shopper_acts_on_their_order(self):
		frappe.set_user(self.other)
		for method in (orders.cancel_order, orders.get_return_options, orders.get_invoice_url):
			with self.subTest(method.__name__), self.assertRaises(frappe.DoesNotExistError):
				method(self.sales_order.name)

		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			orders.cancel_order(self.sales_order.name)
		self.assertEqual(frappe.db.get_value("Sales Order", self.sales_order.name, "docstatus"), 1)

	def test_an_undelivered_order_cannot_be_returned(self):
		frappe.set_user(self.shopper)

		options = orders.get_return_options(self.sales_order.name)

		self.assertEqual(set(options), ReturnOptions.__required_keys__)
		self.assertEqual((options["can_return"], options["return_by"]), (False, None))
		with self.assertRaisesRegex(frappe.ValidationError, "not delivered yet"):
			orders.request_return(self.sales_order.name, [{"item_code": self.item_code, "reason": "Size"}])

	def test_a_delivered_order_is_returned_once(self):
		frappe.db.set_single_value("Commera Settings", "return_period", 30)
		fulfil_order(self.sales_order.name)
		frappe.set_user(self.shopper)

		self.assertTrue(orders.get_return_options(self.sales_order.name)["can_return"])
		options = orders.request_return(
			self.sales_order.name, frappe.as_json([{"item_code": self.item_code, "reason": "Size"}])
		)

		self.assertEqual((options["pending_items"], options["returned_items"]), ([self.item_code], []))
		with self.assertRaisesRegex(frappe.ValidationError, "already been returned"):
			orders.request_return(self.sales_order.name, [{"item_code": self.item_code, "reason": "Size"}])

	def test_return_items_must_be_a_list_of_objects(self):
		frappe.set_user(self.shopper)

		with self.assertRaisesRegex(frappe.ValidationError, "list of objects"):
			orders.request_return(self.sales_order.name, '"everything"')

	def test_the_invoice_link_points_at_the_orders_invoice(self):
		frappe.set_user(self.shopper)
		self.assertIsNone(orders.get_invoice_url(self.sales_order.name))

		frappe.set_user("Administrator")
		invoice = make_sales_invoice(self.sales_order.name)
		invoice.flags.ignore_permissions = True
		invoice.insert()
		invoice.submit()
		frappe.set_user(self.shopper)

		url = orders.get_invoice_url(self.sales_order.name)

		self.assertTrue(url.startswith("/api/method/frappe.utils.print_format.download_pdf?"))
		self.assertIn(f"name={invoice.name}", url)

	def test_a_guest_tracks_an_order_only_with_its_key(self):
		key = set_order_access_key(self.sales_order)
		frappe.set_user("Guest")

		with patch("commera.sdk.account.read_order_tracking", return_value={"has_tracking": False}):
			self.assertEqual(orders.get_order_tracking(self.sales_order.name, key), {"has_tracking": False})
			for wrong_key in (None, "not-the-key"):
				with self.subTest(wrong_key), self.assertRaises(frappe.PermissionError):
					orders.get_order_tracking(self.sales_order.name, wrong_key)

	def test_the_order_link_answers_alike_and_mails_only_a_match(self):
		self.sales_order.db_set("contact_email", self.shopper)
		frappe.set_user("Guest")

		with patch("frappe.sendmail") as sendmail:
			unknown_answer = orders.send_order_link(self.sales_order.name, self.other)
			sendmail.assert_not_called()
			match_answer = orders.send_order_link(self.sales_order.name, f" {self.shopper.upper()} ")

		self.assertEqual(unknown_answer, match_answer)
		sendmail.assert_called_once()

	@property
	def item_code(self) -> str:
		return self.sales_order.items[0].item_code
