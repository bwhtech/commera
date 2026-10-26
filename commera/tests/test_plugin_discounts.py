from unittest.mock import patch

import frappe

from commera.api.payments import (
	CheckoutPriceChangedError,
	drop_refused_codes,
	generate_quotation_for_cart,
)
from commera.discounts.doctype.commera_discount.commera_discount import DiscountCodeError
from commera.sdk import cart as cart_sdk
from commera.sdk import orders as orders_sdk
from commera.tests import test_cart_checkout
from commera.tests.test_discount_codes import CAP_RATE, SHIRT_RATE, DiscountCodeTestCase
from commera.tests.test_payment_hooks import patch_app_hooks
from commera.tests.test_server_cart import list_items


def note_the_cart(event):
	pass


def refuse_zz_codes(quotation, code):
	return "This code's limit was reached." if code.upper().startswith("ZZ") else None


class TestDiscountEvents(DiscountCodeTestCase):
	def setUp(self):
		super().setUp()
		list_items(self.shirt, self.cap)

	def test_a_placed_order_fires_discount_used(self):
		code = self.create_code(percentage=10)

		sales_order = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))

		data = frappe.parse_json(
			frappe.db.get_value(
				"Commera Event", {"event": "discount_used", "reference_name": sales_order.name}, "data"
			)
		)
		self.assertEqual((data["code"], data["amount"]), (code, 9))
		self.assertEqual(data["discounts"][0]["code"], code)

	def test_the_order_snapshot_lists_the_discounts_it_used(self):
		code = self.create_code(percentage=10)

		sales_order = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))

		[allocation] = orders_sdk.get_order(sales_order.name)["discounts"]
		self.assertEqual((allocation["code"], allocation["amount"]), (code, 9))

	def test_a_new_cart_fires_cart_created_only_when_an_app_listens(self):
		frappe.set_user("Administrator")
		cart_sdk.add_lines([{"item_code": self.cap, "qty": 1}])
		quiet_cart = frappe.get_all("Commera Cart", filters={"user": "Administrator"}, pluck="name")[0]
		frappe.delete_doc("Commera Cart", quiet_cart, force=True)
		patch_app_hooks(self, {"commera_events": {"cart_created": [f"{__name__}.note_the_cart"]}})

		cart_sdk.add_lines([{"item_code": self.cap, "qty": 1}])

		new_cart = frappe.get_all("Commera Cart", filters={"user": "Administrator"}, pluck="name")[0]
		self.assertFalse(
			frappe.db.exists("Commera Event", {"event": "cart_created", "reference_name": quiet_cart})
		)
		self.assertTrue(
			frappe.db.exists("Commera Event", {"event": "cart_created", "reference_name": new_cart})
		)


class TestCartAttributes(DiscountCodeTestCase):
	def setUp(self):
		super().setUp()
		list_items(self.shirt, self.cap)
		sale_price_list = frappe.db.get_single_value("Commera Settings", "sale_price_list")
		self.addCleanup(self.set_sale_price_list, sale_price_list)
		self.set_sale_price_list(self.price_list)

	def set_sale_price_list(self, price_list: str):
		frappe.db.set_single_value("Commera Settings", "sale_price_list", price_list)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

	def test_cart_attributes_merge_and_reach_the_order(self):
		cart_sdk.add_lines([{"item_code": self.cap, "qty": 1}])
		cart_sdk.set_cart_attributes({"source": "buy-link", "gift": "yes"})

		priced = cart_sdk.set_cart_attributes({"gift": None})
		quotation = generate_quotation_for_cart(
			{"items": [{"item": {}, "variant": {"item_code": self.cap}, "qty": 1}]}
		)

		self.assertEqual(priced["attributes"], {"source": "buy-link"})
		self.assertEqual(frappe.parse_json(quotation.custom_cart_attributes), {"source": "buy-link"})
		self.assertEqual(self.get_line(quotation, self.cap).rate, CAP_RATE)


class TestValidateDiscountCodeHook(DiscountCodeTestCase):
	def setUp(self):
		super().setUp()
		list_items(self.shirt, self.cap)
		patch_app_hooks(self, {"commera_hooks": {"validate_discount_code": [f"{__name__}.refuse_zz_codes"]}})

	def test_a_refused_code_is_skipped_on_the_cart(self):
		code = self.create_code(percentage=10)

		quotation = self.create_quotation({self.shirt: 1}, (code,))

		self.assertFalse(quotation.custom_code_order_discount)

	def test_a_refused_code_never_reaches_the_order(self):
		code = self.create_code(percentage=10)

		sales_order = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))

		self.assertFalse(sales_order.custom_code_order_discount)
		self.assertEqual(sales_order.net_total, SHIRT_RATE)
		self.assertFalse(frappe.db.exists("Commera Discount Use", {"sales_order": sales_order.name}))

	def test_a_refused_code_cannot_be_added_and_says_why(self):
		code = self.create_code(percentage=10)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])

		with self.assertRaisesRegex(DiscountCodeError, "limit was reached"):
			cart_sdk.add_discount_code(code)

	def test_checkout_removes_a_refused_code_and_tells_the_shopper(self):
		code = self.create_code(percentage=10)
		patch_app_hooks(self, {"commera_hooks": {}})
		quotation = self.create_quotation({self.shirt: 1}, (code,))
		self.assertEqual(quotation.custom_code_order_discount, 9)
		patch_app_hooks(self, {"commera_hooks": {"validate_discount_code": [f"{__name__}.refuse_zz_codes"]}})

		# The removal is committed before the message; a test must not commit its fixtures.
		with (
			patch.object(frappe.db, "commit"),
			self.assertRaisesRegex(CheckoutPriceChangedError, "limit was reached"),
		):
			drop_refused_codes(quotation)

		quotation.reload()
		self.assertFalse(quotation.custom_discount_codes)
		self.assertFalse(quotation.custom_code_order_discount)
