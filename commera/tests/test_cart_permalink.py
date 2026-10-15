import re
from urllib.parse import parse_qsl, urlsplit

import frappe
from frappe.tests import IntegrationTestCase
from frappe.website.page_renderers.redirect_page import RedirectPage
from frappe.website.path_resolver import PathResolver
from frappe.website.serve import get_response_content
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.shop_themes.doctype.shop_theme_settings.shop_theme_settings import DEFAULT_ROUTES
from commera.tests.test_product_details import ProductDetailPriceTestCase
from commera.utils import get_country_list
from commera.www.cart import permalink
from commera.www.cart.checkout import get_checkout_prefill
from commera.www.cart.checkout import get_context as get_checkout_context


class TestParseCartCodes(IntegrationTestCase):
	def test_quantities_merge_and_missing_qty_means_one(self):
		quantities, notices = permalink.parse_cart_codes("SHIRT-M:2,CAP,SHIRT-M:1")

		self.assertEqual(quantities, {"SHIRT-M": 3, "CAP": 1})
		self.assertEqual(notices, [])

	def test_item_code_keeps_everything_before_the_last_colon(self):
		quantities, _ = permalink.parse_cart_codes("A:B:4")

		self.assertEqual(quantities, {"A:B": 4})

	def test_non_positive_or_fractional_quantities_are_skipped_with_a_notice(self):
		quantities, notices = permalink.parse_cart_codes("ZERO:0,NEGATIVE:-1,HALF:1.5,WORD:two,:3,OK:1")

		self.assertEqual(quantities, {"OK": 1})
		self.assertEqual(len(notices), 5)

	def test_lines_beyond_the_cap_are_skipped_under_one_notice(self):
		codes = ",".join(f"ITEM-{index}:1" for index in range(1000))
		quantities, notices = permalink.parse_cart_codes(codes)

		self.assertEqual(len(quantities), permalink.MAX_CART_LINES)
		self.assertNotIn(f"ITEM-{permalink.MAX_CART_LINES}", quantities)
		self.assertEqual(len(notices), 1)
		self.assertIn(str(1000 - permalink.MAX_CART_LINES), notices[0])


class TestCartPermalinkPage(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.clear_document_cache, "Commera Settings", "Commera Settings")
		self.addCleanup(frappe.set_user, "Administrator")
		self.medium = self.make_stocked_item("M", stock_qty=5, default_rate=100, sale_rate=80)
		self.large = self.make_stocked_item("L", stock_qty=0, default_rate=100)
		self.small = self.make_stocked_item("S", stock_qty=2, default_rate=100)
		self.variant = self.make_sized_variant({"M": self.medium, "L": self.large, "S": self.small})

	def make_stocked_item(self, label, stock_qty, default_rate, sale_rate=None):
		item_code = self.make_item(label)
		self.make_item_price(item_code, self.default_price_list, default_rate)
		if sale_rate is not None:
			self.make_item_price(item_code, self.sale_price_list, sale_rate)
		if stock_qty:
			frappe.get_doc(
				{
					"doctype": "Bin",
					"item_code": item_code,
					"warehouse": self.warehouse,
					"actual_qty": stock_qty,
				}
			).insert(ignore_permissions=True)
		return item_code

	def make_sized_variant(self, item_code_by_size):
		variant = frappe.new_doc("Style Attribute Variant")
		variant.configurator = self.configurator
		variant.item_style = self.medium
		variant.item_group = self.item_group
		variant.attribute_value = f"Val {frappe.generate_hash(length=6)}"
		variant.display_name = f"Permalink {self.suffix}"
		variant.route = f"permalink-test-{self.suffix.lower()}"
		variant.append("images", {"image": "/assets/permalink-front.jpg"})
		variant.append("images", {"image": "/assets/permalink-back.jpg"})
		for size, item_code in item_code_by_size.items():
			variant.append("sizes", {"size": size, "item_code": item_code})
		variant.is_published = 1
		variant.insert(ignore_permissions=True)
		return variant

	def render(self, codes, **query):
		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
		frappe.local.form_dict = frappe._dict(codes=codes, **query)
		context = frappe._dict()
		permalink.get_context(context)
		return context

	def test_line_matches_the_shape_the_cart_store_adds(self):
		context = self.render(f"{self.medium}:2")

		self.assertEqual(context.notices, [])
		[line] = context.lines
		self.assertEqual(line["qty"], 2)
		self.assertEqual(line["price"], 80)
		self.assertEqual(line["default_price"], 100)
		self.assertEqual(line["item"]["name"], self.variant.name)
		self.assertEqual(line["item"]["route"], self.variant.route)
		self.assertEqual(
			[image["image"] for image in line["item"]["images"]],
			["/assets/permalink-front.jpg", "/assets/permalink-back.jpg"],
		)
		self.assertEqual(line["variant"]["item_code"], self.medium)
		self.assertEqual(line["variant"]["size"], "M")
		self.assertEqual(line["variant"]["stock_detail"]["stock_qty"], 5)
		self.assertEqual([size["size"] for size in line["sizes"]], ["S", "M", "L"])

	def test_quantity_is_lowered_to_stock_with_a_notice(self):
		context = self.render(f"{self.small}:9")

		self.assertEqual(context.lines[0]["qty"], 2)
		self.assertEqual(len(context.notices), 1)

	def test_out_of_stock_unknown_and_disabled_codes_are_dropped(self):
		frappe.db.set_value("Item", self.small, "disabled", 1)
		context = self.render(f"{self.large}:1,NO-SUCH-ITEM-{self.suffix}:1,{self.small}:1,{self.medium}:1")

		self.assertEqual([line["variant"]["item_code"] for line in context.lines], [self.medium])
		self.assertEqual(len(context.notices), 3)

	def test_unpublished_product_is_not_added(self):
		frappe.db.set_value("Style Attribute Variant", self.variant.name, "is_published", 0)
		context = self.render(f"{self.medium}:1")

		self.assertEqual(context.lines, [])
		self.assertEqual(context.next_url, "/en/cart")

	def test_link_with_nothing_to_add_says_so_instead_of_waiting(self):
		html = get_response_content("en/cart/,,,")

		self.assertIn("This cart link has nothing to add", html)
		self.assertNotIn("Adding the products to your bag", html)

	def test_signed_in_shopper_resumes_checkout_from_the_cart_keeping_campaign_params(self):
		context = self.render(
			f"{self.medium}:1",
			discount="SUMMER10",
			utm_source="newsletter",
			ref="dropped",
			**{"checkout[email]": "shopper@example.com"},
		)

		next_url = urlsplit(context.next_url)
		self.assertEqual(next_url.path, "/en/cart")
		self.assertEqual(
			dict(parse_qsl(next_url.query)),
			{
				"checkout": "1",
				"discount": "SUMMER10",
				"utm_source": "newsletter",
				"checkout[email]": "shopper@example.com",
			},
		)

	def test_guest_goes_to_checkout_only_when_guest_checkout_is_on(self):
		frappe.set_user("Guest")
		for allow_guest_checkout, expected_path in ((1, "/en/cart/checkout"), (0, "/en/cart")):
			frappe.db.set_single_value("Commera Settings", "allow_guest_checkout", allow_guest_checkout)
			frappe.clear_document_cache("Commera Settings", "Commera Settings")
			context = self.render(f"{self.medium}:1", discount="SUMMER10")

			self.assertEqual(urlsplit(context.next_url).path, expected_path)
			self.assertEqual(dict(parse_qsl(urlsplit(context.next_url).query)), {"discount": "SUMMER10"})


class TestBareCartLink(IntegrationTestCase):
	def test_bare_link_redirects_to_english_keeping_item_codes_and_query_encoded(self):
		frappe.local.request = Request(
			EnvironBuilder(
				path="/cart/Will%20You%20Commit%3F-OS:2", query_string="discount=A&utm_source=x"
			).get_environ()
		)
		self.addCleanup(delattr, frappe.local, "request")
		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
		frappe.local.form_dict = frappe._dict(codes="Will You Commit?-OS:2")

		with self.assertRaises(frappe.Redirect):
			permalink.get_context(frappe._dict())
		self.assertEqual(
			frappe.flags.redirect_location, "/en/cart/Will%20You%20Commit%3F-OS:2?discount=A&utm_source=x"
		)


class TestGuestCheckoutRedirect(IntegrationTestCase):
	def test_guest_sent_back_to_the_cart_keeps_the_query_string(self):
		frappe.local.request = Request(
			EnvironBuilder(path="/en/cart/checkout", query_string="discount=A&utm_source=x").get_environ()
		)
		self.addCleanup(delattr, frappe.local, "request")
		frappe.local.lang = "en"
		frappe.set_user("Guest")
		self.addCleanup(frappe.set_user, "Administrator")

		with self.assertRaises(frappe.Redirect):
			get_checkout_context(frappe._dict())
		self.assertEqual(frappe.flags.redirect_location, "/en/cart?discount=A&utm_source=x")


class TestCartRoutes(IntegrationTestCase):
	def resolve(self, path):
		frappe.local.request = Request(EnvironBuilder(path=f"/{path}").get_environ())
		self.addCleanup(delattr, frappe.local, "request")
		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
		frappe.local.form_dict = frappe._dict()
		return PathResolver(path).resolve()

	def test_checkout_is_not_taken_for_a_cart_link(self):
		endpoint, _ = self.resolve("en/cart/checkout")

		self.assertEqual(endpoint, "/cart/checkout.html")

	def test_a_cart_link_resolves_to_the_permalink_page_with_its_codes(self):
		endpoint, _ = self.resolve("en/cart/X:1,Y:2")

		self.assertEqual(endpoint, "/cart/permalink.html")
		self.assertEqual(frappe.form_dict.codes, "X:1,Y:2")

	def test_bare_checkout_still_redirects_to_english(self):
		_, renderer = self.resolve("cart/checkout")

		self.assertIsInstance(renderer, RedirectPage)
		self.assertEqual(frappe.flags.redirect_location, "/en/cart/checkout")

	def test_theme_permalink_route_leaves_checkout_alone(self):
		[pattern] = [
			re.compile(route["url_pattern"])
			for route in DEFAULT_ROUTES
			if route["template_path"] == "pages/cart/permalink.html"
		]

		self.assertIsNone(pattern.match("en/cart/checkout"))
		self.assertEqual(pattern.match("en/cart/X:1")["codes"], "X:1")


class TestCheckoutPrefill(IntegrationTestCase):
	def prefill(self, **query):
		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
		frappe.local.form_dict = frappe._dict(query)
		return get_checkout_prefill(get_country_list())

	def test_shopify_params_map_onto_checkout_fields(self):
		prefill = self.prefill(
			**{
				"checkout[email]": " shopper@example.com ",
				"checkout[shipping_address][address1]": "1 King Road",
				"checkout[shipping_address][address2]": "Flat 4",
				"checkout[shipping_address][province]": "Riyadh Province",
				"checkout[shipping_address][zip]": "12345",
				"checkout[shipping_address][country]": "SA",
				"checkout[shipping_address][first_name]": "",
				"checkout[note]": "ignored",
			}
		)

		self.assertEqual(
			prefill,
			{
				"email": "shopper@example.com",
				"full_address": "1 King Road",
				"landmark": "Flat 4",
				"state": "Riyadh Province",
				"po_box": "12345",
				"country": "Saudi Arabia",
			},
		)

	def test_unknown_country_is_left_for_the_shopper(self):
		self.assertEqual(self.prefill(**{"checkout[shipping_address][country]": "Atlantis"}), {})
