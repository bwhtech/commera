from unittest.mock import patch

import frappe
from frappe.auth import CookieManager
from frappe.utils.data import add_days, now_datetime
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.api.payments import generate_quotation_for_cart, save_cart_quotation
from commera.api.server_cart import (
	apply_discount_code,
	get_priced_server_cart,
	get_server_cart,
	remove_discount_code,
	sync_server_cart,
)
from commera.api.shipping import apply_delivery_option, get_checkout_summary
from commera.commera_ecommerce.doctype.commera_cart.commera_cart import (
	ABANDONED_GUEST_CART_DAYS,
	MAX_LINE_QUANTITY,
	clear_ordered_cart,
	delete_abandoned_guest_carts,
	get_session_cart,
	keep_guest_cart,
)
from commera.core import _get_cart_quotation
from commera.discounts.codes import generate_codes, get_code_discount
from commera.discounts.shipping import apply_shipping_discounts
from commera.guest import CART_TOKEN_HEADER, GUEST_CART_COOKIE
from commera.sdk import cart as cart_sdk
from commera.tests.test_delivery_option_charges import make_store_rule, set_store_rule
from commera.tests.test_discount_codes import CAP_RATE, SHIRT_RATE, DiscountCodeTestCase
from commera.www.cart.checkout import cart_needs_refresh, refresh_checkout_cart, set_cart_context


class TestServerCart(DiscountCodeTestCase):
	def setUp(self):
		super().setUp()
		sale_price_list = frappe.db.get_single_value("Commera Settings", "sale_price_list")
		self.addCleanup(self.set_sale_price_list, sale_price_list)
		self.set_sale_price_list(self.price_list)
		# The cart SDK sells only items of a published product.
		list_items(self.shirt, self.cap)
		self.shopper = self.create_shopper()
		frappe.set_user(self.shopper)

	def set_sale_price_list(self, price_list: str):
		frappe.db.set_single_value("Commera Settings", "sale_price_list", price_list)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

	def create_shopper(self) -> str:
		email = f"zz-cart-{frappe.generate_hash(length=8)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "ZZ Cart",
				"send_welcome_email": 0,
				"user_type": "Website User",
			}
		)
		user.append("roles", {"role": "Customer"})
		user.insert(ignore_permissions=True)
		return email

	def browser_line(self, item_code: str, qty: int) -> dict:
		return {"item": {"display_name": item_code}, "variant": {"item_code": item_code}, "qty": qty}

	def test_lines_merge_only_when_item_and_attributes_match(self):
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1, "attributes": {"engraving": "AB"}}])
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 2, "attributes": {"engraving": "AB"}}])

		priced = cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])

		self.assertEqual(
			[(line["qty"], line["attributes"]) for line in priced["lines"]],
			[(3, {"engraving": "AB"}), (1, {})],
		)

	def test_browser_quantities_keep_line_attributes(self):
		cart_sdk.add_lines(
			[
				{"item_code": self.shirt, "qty": 1, "attributes": {"gift": "yes"}},
				{"item_code": self.cap, "qty": 1},
			]
		)
		cart = get_session_cart()

		self.assertTrue(cart.set_quantities({self.shirt: 3}))

		self.assertEqual([(row.item_code, row.qty) for row in cart.lines], [(self.shirt, 3)])
		self.assertEqual(frappe.parse_json(cart.lines[0].attributes), {"gift": "yes"})

	def test_a_stale_browser_does_not_overwrite_the_server_cart(self):
		version = sync_server_cart([{"item_code": self.shirt, "qty": 1}])["version"]
		server_version = cart_sdk.add_lines([{"item_code": self.cap, "qty": 1}])["version"]

		response = sync_server_cart([{"item_code": self.shirt, "qty": 5}], version)

		self.assertTrue(response["conflict"])
		self.assertEqual(response["version"], server_version)
		self.assertEqual(
			{(row.item_code, row.qty) for row in get_session_cart().lines}, {(self.shirt, 1), (self.cap, 1)}
		)

	def test_a_cart_link_replaces_a_cart_changed_on_another_device(self):
		stale_version = sync_server_cart([{"item_code": self.shirt, "qty": 1}])["version"]
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 2}])
		link_lines = [{"item_code": self.cap, "qty": 4}]
		self.assertTrue(sync_server_cart(link_lines, stale_version)["conflict"])

		response = sync_server_cart(link_lines, get_server_cart()["version"])

		self.assertNotIn("conflict", response)
		self.assertEqual([(row.item_code, row.qty) for row in get_session_cart().lines], [(self.cap, 4)])

	def test_sync_refuses_more_than_the_stock(self):
		self.assertTrue(sync_server_cart([{"item_code": self.shirt, "qty": 10}])["version"])

		with self.assertRaisesRegex(frappe.ValidationError, "out of stock"):
			sync_server_cart([{"item_code": self.shirt, "qty": 11}])

	def test_an_app_cannot_add_more_than_the_stock(self):
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 10}])

		with self.assertRaisesRegex(frappe.ValidationError, "out of stock"):
			cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])
		with self.assertRaisesRegex(frappe.ValidationError, "out of stock"):
			cart_sdk.update_lines([{"line_id": get_session_cart().lines[0].name, "qty": 11}])

	def test_a_line_that_ran_out_does_not_block_other_edits(self):
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 5}])
		self.set_stock(self.shirt, 1)

		priced = cart_sdk.add_lines([{"item_code": self.cap, "qty": 1}])

		self.assertEqual(
			{(line["item_code"], line["qty"]) for line in priced["lines"]}, {(self.shirt, 5), (self.cap, 1)}
		)

	def test_sign_in_caps_the_merged_cart_at_the_stock(self):
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 6}])
		self.use_guest_cart()
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 6}])

		frappe.set_user(self.shopper)
		keep_guest_cart()

		self.assertEqual([(row.item_code, row.qty) for row in get_session_cart().lines], [(self.shirt, 10)])

	def test_a_placed_order_clears_the_ordered_lines_from_the_server_cart(self):
		cart_sdk.add_lines(
			[{"item_code": self.shirt, "qty": 1}, {"item_code": self.cap, "qty": 1, "selected": 0}]
		)
		version = get_session_cart().version

		clear_ordered_cart(frappe._dict(custom_guest_cart_key=None), self.shopper)

		cart = get_session_cart()
		self.assertEqual([row.item_code for row in cart.lines], [self.cap])
		self.assertEqual(cart.version, version)

	def test_abandoned_guest_carts_are_deleted(self):
		self.use_guest_cart()
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])
		guest_cart = get_session_cart().name
		frappe.set_user(self.shopper)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])
		account_cart = get_session_cart().name
		old = add_days(now_datetime(), -ABANDONED_GUEST_CART_DAYS - 1)
		frappe.db.set_value(
			"Commera Cart",
			{"name": ["in", [guest_cart, account_cart]]},
			"modified",
			old,
			update_modified=False,
		)

		with patch.object(frappe.db, "commit"):
			delete_abandoned_guest_carts()

		self.assertFalse(frappe.db.exists("Commera Cart", guest_cart))
		self.assertFalse(frappe.db.exists("Commera Cart Line", {"parent": guest_cart}))
		self.assertTrue(frappe.db.exists("Commera Cart", account_cart))

	def test_a_cart_line_holds_a_limited_quantity(self):
		self.set_stock(self.shirt, 1000)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": MAX_LINE_QUANTITY}])

		with self.assertRaisesRegex(frappe.ValidationError, "at most"):
			cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])

	def test_the_store_sets_how_many_units_a_cart_line_holds(self):
		previous = frappe.db.get_single_value("Commera Settings", "max_cart_line_quantity")
		self.addCleanup(self.set_max_line_quantity, previous)
		self.set_max_line_quantity(250)
		self.set_stock(self.shirt, 1000)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 250}])
		with self.assertRaisesRegex(frappe.ValidationError, "at most 250"):
			cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])

		self.set_max_line_quantity(0)
		with self.assertRaisesRegex(frappe.ValidationError, f"at most {MAX_LINE_QUANTITY} "):
			cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])

	def set_stock(self, item_code: str, qty: float):
		frappe.db.set_value("Bin", {"item_code": item_code, "warehouse": self.warehouse}, "actual_qty", qty)

	def set_max_line_quantity(self, quantity: int):
		frappe.db.set_single_value("Commera Settings", "max_cart_line_quantity", quantity)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

	def test_sign_in_makes_the_guest_cart_the_account_cart(self):
		code = self.create_code(amount=10)
		self.use_guest_cart()
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])
		cart_sdk.add_discount_code(code)

		frappe.set_user(self.shopper)
		keep_guest_cart()

		cart = get_session_cart()
		self.assertEqual([(row.item_code, row.qty) for row in cart.lines], [(self.shirt, 1)])
		self.assertEqual(cart.discount_codes, code)
		self.assertIsNone(cart.cart_key)
		self.assertIn(GUEST_CART_COOKIE, frappe.local.cookie_manager.to_delete)

	def test_sign_in_merges_the_guest_cart_into_the_account_cart(self):
		code = self.create_code(amount=10)
		cart_sdk.add_lines([{"item_code": self.cap, "qty": 1}])
		account_cart = get_session_cart().name
		self.use_guest_cart()
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 2}])
		cart_sdk.add_discount_code(code)
		guest_cart = get_session_cart().name

		frappe.set_user(self.shopper)
		keep_guest_cart()

		cart = get_session_cart()
		self.assertEqual(cart.name, account_cart)
		self.assertEqual({(row.item_code, row.qty) for row in cart.lines}, {(self.cap, 1), (self.shirt, 2)})
		self.assertEqual(cart.discount_codes, code)
		self.assertFalse(frappe.db.exists("Commera Cart", guest_cart))

	def use_guest_cart(
		self,
		token: str | None = None,
		header: bool = False,
		path: str = "/api/method/commera.api.storefront.cart.get_cart",
	):
		token = token or frappe.generate_hash(length=32)
		headers = {CART_TOKEN_HEADER: token} if header else {"Cookie": f"{GUEST_CART_COOKIE}={token}"}
		if not hasattr(frappe.local, "request"):
			self.addCleanup(delattr, frappe.local, "request")
		frappe.local.request = Request(EnvironBuilder(path=path, headers=headers).get_environ())
		frappe.local.cookie_manager = CookieManager()
		frappe.set_user("Guest")

	def test_a_cart_token_header_finds_the_same_guest_cart_as_the_cookie(self):
		token = frappe.generate_hash(length=32)
		self.use_guest_cart(token)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 2}])
		cookie_cart = get_session_cart().name

		self.use_guest_cart(token, header=True)

		self.assertEqual(get_session_cart().name, cookie_cart)

	def test_the_cart_token_header_reaches_only_the_storefront_api(self):
		token = frappe.generate_hash(length=32)
		self.use_guest_cart(token)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])

		for path in ("/en/cart/checkout", "/api/method/commera.api.payments.save_cart_quotation"):
			with self.subTest(path):
				self.use_guest_cart(token, header=True, path=path)
				self.assertIsNone(get_session_cart())

	def test_a_short_cart_token_header_is_refused(self):
		self.use_guest_cart("too-short", header=True)

		with self.assertRaisesRegex(frappe.ValidationError, "32 to 128"):
			get_session_cart()

	def test_the_priced_cart_shows_line_and_order_discounts(self):
		product = self.create_code(percentage=10, item_codes=(self.shirt,), combines_with_order=1)
		order = self.create_code(amount=10, combines_with_product=1)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 2}, {"item_code": self.cap, "qty": 1}])
		cart_sdk.add_discount_code(product.lower())

		priced = cart_sdk.add_discount_code(order)

		shirt = next(line for line in priced["lines"] if line["item_code"] == self.shirt)
		self.assertEqual((shirt["rate"], shirt["code_discount"]), (81, 9))
		self.assertEqual(shirt["discount"], get_code_discount(product))
		self.assertEqual([state["applied"] for state in priced["discount_codes"]], [True, True])
		self.assertEqual(priced["subtotal"], 2 * 81 + CAP_RATE)
		self.assertEqual(priced["order_discount"], 10)
		self.assertEqual(priced["total"], 2 * 81 + CAP_RATE - 10)

	def test_checkout_takes_attributes_and_codes_from_the_server_cart(self):
		code = self.create_code(amount=10, item_codes=(self.shirt,))
		cart_sdk.add_lines(
			[
				{"item_code": self.shirt, "qty": 1, "attributes": {"engraving": "AB"}},
				{"item_code": self.shirt, "qty": 1, "attributes": {"engraving": "CD"}},
			]
		)
		cart_sdk.add_discount_code(code)

		quotation = generate_quotation_for_cart({"items": [self.browser_line(self.shirt, 2)]})

		self.assertEqual(
			[(row.qty, frappe.parse_json(row.custom_line_attributes)) for row in quotation.items],
			[(1, {"engraving": "AB"}), (1, {"engraving": "CD"})],
		)
		self.assertEqual({row.rate for row in quotation.items}, {SHIRT_RATE - 10})
		self.assertEqual(quotation.custom_discount_codes, code)

	def test_checkout_keeps_an_order_code(self):
		code = self.create_code(amount=10)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])
		cart_sdk.add_discount_code(code)

		quotation = generate_quotation_for_cart({"items": [self.browser_line(self.shirt, 1)]})

		self.assertEqual(quotation.custom_code_order_discount, 10)
		self.assertEqual(quotation.net_total, SHIRT_RATE - 10)

	def test_a_code_applied_at_checkout_reaches_the_checkout(self):
		code = self.create_code(amount=10)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])
		generate_quotation_for_cart({"items": [self.browser_line(self.shirt, 1)]})

		response = apply_discount_code(code.lower())

		quotation = _get_cart_quotation()
		self.assertEqual(quotation.custom_discount_codes, code)
		self.assertEqual(quotation.net_total, SHIRT_RATE - 10)
		self.assertEqual(response["checkout_summary"]["discount_amount"], 10)

	def test_a_code_removed_at_checkout_leaves_the_checkout(self):
		code = self.create_code(amount=10)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])
		cart_sdk.add_discount_code(code)
		generate_quotation_for_cart({"items": [self.browser_line(self.shirt, 1)]})

		response = remove_discount_code(code)

		quotation = _get_cart_quotation()
		self.assertFalse(quotation.custom_discount_codes)
		self.assertEqual(quotation.net_total, SHIRT_RATE)
		self.assertEqual(response["checkout_summary"]["discount_amount"], 0)

	def test_a_code_change_at_checkout_reprices_the_delivery_discount(self):
		self.set_charge_account_head()
		frappe.set_user("Administrator")
		frappe.db.set_value("Commera Discount", {"method": "Automatic"}, "enabled", 0)
		free_shipping = self.create_code(discount_type="Free Shipping", shipping_percentage=100)
		frappe.set_user(self.shopper)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])
		cart_sdk.add_discount_code(free_shipping)
		generate_quotation_for_cart({"items": [self.browser_line(self.shirt, 1)]})
		quotation = _get_cart_quotation()
		option = {"title": "Standard", "amount": 60}
		apply_delivery_option(quotation, apply_shipping_discounts(quotation, [option])[0])
		save_cart_quotation(quotation)
		self.assertEqual(_get_cart_quotation().custom_delivery_charge, 0)

		remove_discount_code(free_shipping)

		quotation = _get_cart_quotation()
		self.assertEqual((quotation.custom_delivery_charge, quotation.custom_shipping_discount), (60, 0))
		self.assertFalse(quotation.custom_shipping_discount_id)

	def test_free_delivery_is_judged_after_discounts_in_cart_and_checkout(self):
		self.addCleanup(set_store_rule, frappe.db.get_single_value("Commera Settings", "shipping_rule"))
		frappe.set_user("Administrator")
		make_store_rule(
			[
				{"from_value": 0, "to_value": 100, "shipping_amount": 50},
				{"from_value": 100, "to_value": 0, "shipping_amount": 0, "free_shipping": 1},
			]
		)
		code = self.create_code(amount=40)
		frappe.set_user(self.shopper)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}, {"item_code": self.cap, "qty": 1}])
		self.assertEqual(cart_sdk.get_priced_cart()["free_delivery_shortfall"], 0)

		priced = cart_sdk.add_discount_code(code)
		generate_quotation_for_cart(
			{"items": [self.browser_line(self.shirt, 1), self.browser_line(self.cap, 1)]}
		)
		summary = get_checkout_summary(_get_cart_quotation())

		self.assertEqual((priced["free_delivery_above"], priced["free_delivery_shortfall"]), (100, 10))
		self.assertEqual((summary["free_delivery_above"], summary["free_delivery_shortfall"]), (100, 10))
		self.assertEqual(summary["shipping"], 50)

	def test_a_band_charging_nothing_counts_as_free_delivery(self):
		self.addCleanup(set_store_rule, frappe.db.get_single_value("Commera Settings", "shipping_rule"))
		frappe.set_user("Administrator")
		make_store_rule(
			[
				{"from_value": 0, "to_value": 999, "shipping_amount": 99},
				{"from_value": 999, "to_value": 0, "shipping_amount": 0},
			]
		)
		frappe.set_user(self.shopper)

		priced = cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])

		self.assertEqual(
			(priced["free_delivery_above"], priced["free_delivery_shortfall"]), (999, 999 - SHIRT_RATE)
		)

	def test_a_code_that_does_not_apply_yet_says_why(self):
		code = self.create_code(percentage=10, minimum_requirement="Subtotal", minimum_subtotal=500)
		cart_sdk.add_lines([{"item_code": self.cap, "qty": 1}])

		state = cart_sdk.add_discount_code(code)["discount_codes"][0]

		self.assertFalse(state["applied"])
		self.assertIn("more to use", state["reason"])

	def test_a_code_with_nothing_to_discount_says_so(self):
		code = self.create_code(percentage=10, item_codes=(self.shirt,))
		cart_sdk.add_lines([{"item_code": self.cap, "qty": 1}])

		state = cart_sdk.add_discount_code(code)["discount_codes"][0]

		self.assertIn("Nothing in your cart qualifies", state["reason"])

	def test_a_deleted_or_renamed_code_drops_off_with_a_message(self):
		deleted = self.create_code(amount=10)
		renamed = self.create_code(amount=5, combines_with_order=1)
		frappe.db.set_value("Commera Discount", get_code_discount(deleted), "combines_with_order", 1)
		kept = self.create_code(amount=3, combines_with_order=1)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])
		cart_sdk.add_discount_code(deleted)
		cart_sdk.add_discount_code(renamed)
		frappe.set_user("Administrator")
		frappe.delete_doc("Commera Discount Code", deleted, force=True)
		frappe.rename_doc("Commera Discount Code", renamed, f"{renamed}NEW", force=True)
		frappe.set_user(self.shopper)

		priced = cart_sdk.get_priced_cart()

		self.assertEqual(
			[(state["code"], state["applied"]) for state in priced["discount_codes"]],
			[(deleted, False), (renamed, False)],
		)
		self.assertIn("no longer a valid", priced["discount_codes"][0]["reason"])
		self.assertEqual(priced["total"], SHIRT_RATE)

		priced = cart_sdk.add_discount_code(kept)

		self.assertEqual([state["code"] for state in priced["discount_codes"]], [kept])
		self.assertEqual(priced["total"], SHIRT_RATE - 3)

	def test_a_code_that_saves_less_stays_on_the_cart_and_says_why(self):
		smaller = self.create_code(amount=5)
		bigger = self.create_code(amount=8)
		cart_sdk.add_lines([{"item_code": self.cap, "qty": 1}])
		cart_sdk.add_discount_code(smaller)

		priced = cart_sdk.add_discount_code(bigger)

		states = {state["code"]: state for state in priced["discount_codes"]}
		self.assertTrue(states[bigger]["applied"])
		self.assertFalse(states[smaller]["applied"])
		self.assertIn(f"doesn't combine with {bigger}, which saves you more", states[smaller]["reason"])
		self.assertEqual(priced["total"], CAP_RATE - 8)

	def test_a_code_that_saves_the_same_says_only_that_it_does_not_combine(self):
		first = self.create_code(amount=5)
		second = self.create_code(amount=5)
		cart_sdk.add_lines([{"item_code": self.cap, "qty": 1}])
		cart_sdk.add_discount_code(first)

		priced = cart_sdk.add_discount_code(second)

		states = {state["code"]: state for state in priced["discount_codes"]}
		self.assertTrue(states[first]["applied"])
		self.assertTrue(states[second]["reason"].endswith(f"doesn't combine with {first}."))
		self.assertEqual(priced["total"], CAP_RATE - 5)

	def test_a_code_that_gives_nothing_does_not_block_another(self):
		waiting = self.create_code(percentage=10, minimum_requirement="Subtotal", minimum_subtotal=500)
		other = self.create_code(amount=5)
		cart_sdk.add_lines([{"item_code": self.cap, "qty": 1}])
		cart_sdk.add_discount_code(waiting)

		priced = cart_sdk.add_discount_code(other)

		states = {state["code"]: state for state in priced["discount_codes"]}
		self.assertTrue(states[other]["applied"])
		self.assertIn("more to use", states[waiting]["reason"])
		self.assertEqual(priced["total"], CAP_RATE - 5)

	def test_a_code_that_cannot_apply_gives_its_own_reason(self):
		combines = {"combines_with_order": 1, "combines_with_shipping": 1}
		single_use = generate_codes(self.create_discount(amount=5, **combines), 1)[0]
		limited = self.create_code(amount=5, usage_limit=1, **combines)
		shipping = self.create_code(discount_type="Free Shipping", shipping_percentage=100, **combines)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])
		for code in (single_use, limited, shipping):
			cart_sdk.add_discount_code(code)
		frappe.set_user("Administrator")
		self.place_order(self.create_quotation({self.shirt: 1}, (single_use, limited)))
		frappe.set_user(self.shopper)

		reasons = {state["code"]: state["reason"] for state in cart_sdk.get_priced_cart()["discount_codes"]}

		self.assertIn("has already been used", reasons[single_use])
		self.assertIn("has been used up", reasons[limited])
		self.assertIn("once you choose a delivery option", reasons[shipping])

	def test_checkout_without_a_server_cart_is_unchanged(self):
		quotation = generate_quotation_for_cart({"items": [self.browser_line(self.cap, 2)]})

		self.assertEqual(
			[(row.item_code, row.qty, row.rate) for row in quotation.items], [(self.cap, 2, CAP_RATE)]
		)
		self.assertFalse(quotation.custom_discount_codes)

	def test_the_checkout_ticks_are_kept_on_the_server_cart(self):
		sync_server_cart([{"item_code": self.shirt, "qty": 1}, {"item_code": self.cap, "qty": 2}])
		version = get_server_cart()["version"]

		response = sync_server_cart(
			[{"item_code": self.shirt, "qty": 1, "selected": False}, {"item_code": self.cap, "qty": 2}],
			version,
		)

		self.assertNotEqual(response["version"], version)
		self.assertEqual(
			{line["item_code"]: line["selected"] for line in cart_sdk.get_priced_cart()["lines"]},
			{self.shirt: False, self.cap: True},
		)

	def test_the_priced_cart_discounts_only_the_ticked_lines(self):
		code = self.create_code(percentage=10)
		sync_server_cart(
			[{"item_code": self.shirt, "qty": 2}, {"item_code": self.cap, "qty": 1, "selected": False}]
		)

		priced = cart_sdk.add_discount_code(code)

		cap = next(line for line in priced["lines"] if line["item_code"] == self.cap)
		self.assertEqual((cap["rate"], cap["code_discount"], cap["amount"]), (CAP_RATE, 0, CAP_RATE))
		self.assertEqual(priced["subtotal"], 2 * SHIRT_RATE)
		self.assertEqual(priced["total"], 2 * SHIRT_RATE * 0.9)
		self.assertEqual([row["amount"] for row in priced["discounts"]], [2 * SHIRT_RATE * 0.1])

	def test_checkout_takes_only_the_ticked_lines(self):
		sync_server_cart(
			[{"item_code": self.shirt, "qty": 1}, {"item_code": self.cap, "qty": 1, "selected": False}]
		)

		quotation = generate_quotation_for_cart(
			{"items": [self.browser_line(self.shirt, 1), self.browser_line(self.cap, 1)]}
		)

		self.assertEqual([(row.item_code, row.qty) for row in quotation.items], [(self.shirt, 1)])

	def test_opening_checkout_asks_the_page_to_rebuild_a_changed_cart_and_writes_nothing(self):
		sync_server_cart([{"item_code": self.shirt, "qty": 1}])
		generate_quotation_for_cart({"items": [self.browser_line(self.shirt, 1)]})
		cart_sdk.add_lines([{"item_code": self.cap, "qty": 2}])
		context = frappe._dict()

		set_cart_context(context, frappe.get_cached_doc("Commera Settings"))

		self.assertTrue(context.cart_needs_refresh)
		self.assertEqual([(row.item_code, row.qty) for row in _get_cart_quotation().items], [(self.shirt, 1)])
		self.assertFalse(frappe.local.flags.commit)

	def test_the_checkout_page_can_rebuild_the_cart_with_a_post(self):
		sync_server_cart([{"item_code": self.shirt, "qty": 1}])
		generate_quotation_for_cart({"items": [self.browser_line(self.shirt, 1)]})
		self.assertEqual(refresh_checkout_cart(), {"refreshed": False, "redirect": None})
		cart_sdk.add_lines([{"item_code": self.cap, "qty": 2}])
		self.assertTrue(cart_needs_refresh(_get_cart_quotation()))

		self.assertEqual(refresh_checkout_cart(), {"refreshed": True, "redirect": None})

		self.assertEqual(
			{(row.item_code, row.qty) for row in _get_cart_quotation().items},
			{(self.shirt, 1), (self.cap, 2)},
		)
		sync_server_cart([])
		self.assertEqual(refresh_checkout_cart()["redirect"], f"/{frappe.local.lang}/cart")

	def test_an_emptied_server_cart_checks_out_nothing(self):
		sync_server_cart([{"item_code": self.shirt, "qty": 1}])
		generate_quotation_for_cart({"items": [self.browser_line(self.shirt, 1)]})
		sync_server_cart([])

		with self.assertRaises(frappe.ValidationError):
			generate_quotation_for_cart({"items": [self.browser_line(self.shirt, 1)]})
		self.assertEqual(refresh_checkout_cart()["redirect"], f"/{frappe.local.lang}/cart")

	def test_opening_checkout_leaves_a_cart_in_payment_alone(self):
		sync_server_cart([{"item_code": self.shirt, "qty": 1}])
		quotation = generate_quotation_for_cart({"items": [self.browser_line(self.shirt, 1)]})
		self.create_pending_payment_request(quotation.name)
		cart_sdk.add_lines([{"item_code": self.cap, "qty": 2}])

		with patch(
			"bwh_payments.bwh_payments.doctype.gateway_payment_request.gateway_payment_request"
			".GatewayPaymentRequest.release_if_unpaid",
			return_value=False,
		):
			self.assertEqual(refresh_checkout_cart(), {"refreshed": False, "redirect": None})

		self.assertEqual([(row.item_code, row.qty) for row in _get_cart_quotation().items], [(self.shirt, 1)])

	def create_pending_payment_request(self, quotation_name: str):
		payment_request = frappe.new_doc("Gateway Payment Request")
		payment_request.update(
			{
				"name": frappe.generate_hash(length=10),
				"ref_doctype": "Quotation",
				"ref_docname": quotation_name,
				"status": "Pending",
			}
		)
		# db_insert, not insert(): insert() opens a real gateway session.
		payment_request.db_insert()

	def test_sign_in_keeps_the_guest_cart_ticks(self):
		cart_sdk.add_lines([{"item_code": self.cap, "qty": 1}])
		self.use_guest_cart()
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 2, "selected": False}])

		frappe.set_user(self.shopper)
		keep_guest_cart()

		self.assertEqual(
			{(row.item_code, row.selected) for row in get_session_cart().lines},
			{(self.cap, 1), (self.shirt, 0)},
		)

	def test_a_negative_or_fractional_quantity_is_refused(self):
		for qty in (-5, 0.5):
			with self.assertRaises(frappe.ValidationError):
				sync_server_cart([{"item_code": self.shirt, "qty": qty}])

		self.assertIsNone(get_session_cart())

	def test_an_unknown_item_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			sync_server_cart([{"item_code": f"ZZ-NO-SUCH-{frappe.generate_hash(length=6)}", "qty": 1}])

	def test_the_storefront_applies_and_removes_a_code_in_any_case(self):
		code = self.create_code(percentage=10)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])

		applied = apply_discount_code(f" {code.lower()} ")
		removed = remove_discount_code(code.lower())

		self.assertEqual(
			[(state["code"], state["applied"]) for state in applied["discount_codes"]], [(code, True)]
		)
		self.assertEqual(applied["total"], 81)
		self.assertEqual((removed["discount_codes"], removed["total"]), ([], SHIRT_RATE))


def list_items(*item_codes: str):
	for item_code in item_codes:
		list_item(item_code)


def list_item(item_code: str):
	variant = frappe.get_doc(
		{
			"doctype": "Style Attribute Variant",
			"name": f"ZZ-CART-{frappe.generate_hash(length=8)}",
			"item_style": item_code,
			"attribute_value": "Red",
			"display_name": "ZZ Cart Variant",
			"is_published": 1,
		}
	)
	variant.db_insert()
	frappe.get_doc(
		{
			"doctype": "Color Size Item",
			"name": frappe.generate_hash(length=10),
			"parent": variant.name,
			"parenttype": "Style Attribute Variant",
			"parentfield": "sizes",
			"size": "S",
			"item_code": item_code,
		}
	).db_insert()
