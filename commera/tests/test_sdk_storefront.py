import os
from urllib.parse import quote

import frappe
from PIL import Image
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.api.storefront import images
from commera.api.storefront import search as search_api
from commera.sdk import catalog, format, shop
from commera.sdk.types import Menu, MenuItem, ProductCard, SearchResults, Typeahead
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_product_details import ProductDetailPriceTestCase
from commera.tests.test_storefront_api import get_shopper_messages


class TestSdkStorefront(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		frappe.local.commera_storefront_menu = None
		self.addCleanup(setattr, frappe.local, "commera_storefront_menu", None)

	def assert_shape(self, result: dict, shape):
		self.assertEqual(set(result), shape.__required_keys__ | shape.__optional_keys__)

	def make_tab(self, enabled=1) -> str:
		category = frappe.new_doc("Ecommerce Category")
		category.category_name = f"Reads Tab {frappe.generate_hash(length=8)}"
		category.enabled = enabled
		category.link_type = "Item Group"
		category.append("link_item_groups", {"item_group": self.item_group})
		category.insert(ignore_permissions=True)
		frappe.local.commera_storefront_menu = None
		return category.display_name

	def test_main_menu_items_carry_their_storefront_url(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		self.use_request("/ar/products")
		title = self.make_tab()
		hidden_title = self.make_tab(enabled=0)
		menu = shop.get_menu("main-menu")

		self.assert_shape(menu, Menu)
		tab = next(item for item in menu["items"] if item["title"] == title)
		self.assert_shape(tab, MenuItem)
		self.assertEqual(tab["type"], "collection")
		self.assertEqual(
			tab["url"], f"/ar/products?category={tab['target']}&subcategory={quote(self.item_group)}"
		)
		self.assertNotIn(hidden_title, [item["title"] for item in menu["items"]])
		self.assertEqual(shop.get_shop()["menu"], menu["items"])

	def test_the_shop_names_the_store_companys_country(self):
		company = frappe.get_cached_value("Commera Settings", "Commera Settings", "company")
		self.assertEqual(shop.get_shop()["country"], frappe.get_cached_value("Company", company, "country"))

	def test_footer_menu_nests_each_sections_links(self):
		menu = shop.get_menu("footer")

		self.assert_shape(menu, Menu)
		self.assertEqual(
			[(item["title"], [link["url"] for link in item["items"]]) for item in menu["items"]],
			[
				(section["title"], [link["url"] for link in section["links"]])
				for section in shop.get_shop()["footer"]
			],
		)
		self.assertIsNone(shop.get_menu("sidebar"))

	def test_search_finds_a_product_and_an_empty_query_finds_nothing(self):
		route = self.make_priced_variant("SEARCH", default_rate=40)
		results = catalog.search(self.suffix[:3], page_size=48)

		self.assert_shape(results, SearchResults)
		self.assertEqual(results["query"], self.suffix[:3])
		self.assertIn(route, [product["handle"] for product in results["products"]])
		self.assert_shape(results["products"][0], ProductCard)

		empty = catalog.search("  ")
		self.assert_shape(empty, SearchResults)
		self.assertEqual((empty["products"], empty["total"]), ([], 0))

	def test_typeahead_returns_product_cards(self):
		route = self.make_priced_variant("TYPEAHEAD", default_rate=40)
		typeahead = search_api.get_typeahead(self.suffix[:3], limit=20)

		self.assert_shape(typeahead, Typeahead)
		self.assertIn(route, [product["handle"] for product in typeahead["products"]])
		self.assert_shape(typeahead["products"][0], ProductCard)
		self.assertEqual(catalog.get_typeahead("")["products"], [])

	def test_recommendations_are_other_styles_of_the_same_item_group(self):
		route = self.make_priced_variant("SHOWN", default_rate=40)
		same_style = self.make_priced_variant("SAMESTYLE", default_rate=40)
		other_style = self.make_priced_variant("OTHERSTYLE", default_rate=40)
		frappe.db.set_value("Style Attribute Variant", {"route": other_style}, "configurator", "Other Style")

		handles = [product["handle"] for product in search_api.get_recommendations(route)]

		self.assertEqual(handles, [other_style])
		self.assertNotIn(same_style, handles)
		self.assertEqual(catalog.get_recommendations("no-such-product"), [])

	def test_recommendations_are_empty_when_the_item_group_has_no_other_style(self):
		route = self.make_priced_variant("LONESTYLE", default_rate=40)
		frappe.db.set_value("Style Attribute Variant", {"route": route}, "item_group", "Services")

		self.assertEqual(catalog.get_recommendations(route), [])

	def test_newsletter_subscribe_adds_the_email_once_and_clears_an_unsubscribe(self):
		email = f"news-{self.suffix}@example.com"
		member = {"email_group": shop.NEWSLETTER_EMAIL_GROUP, "email": email}

		shop.subscribe_to_newsletter(f" {email} ")
		frappe.db.set_value("Email Group Member", member, "unsubscribed", 1)
		shop.subscribe_to_newsletter(email)

		self.assertEqual(frappe.db.count("Email Group Member", member), 1)
		self.assertEqual(frappe.db.get_value("Email Group Member", member, "unsubscribed"), 0)
		self.assertRaises(frappe.InvalidEmailAddressError, shop.subscribe_to_newsletter, "not-an-email")

	def test_money_uses_the_storefront_currency_symbol(self):
		symbol = frappe.db.get_value("Currency", "INR", "symbol")
		self.assertEqual(format.money(1234.5, "INR"), f"{symbol}1,234.50")
		self.assertEqual(
			format.money(10, "SAR"),
			"\u20c1\u00a010.00",
		)

	def test_product_url_links_the_handle_in_the_current_language(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		self.use_request("/products")
		self.assertEqual(format.product_url("blue shirt"), "/products/blue%20shirt")
		self.use_request("/ar/products")
		self.assertEqual(format.product_url("shirt"), "/ar/products/shirt")
		self.assertRaises(frappe.ValidationError, format.product_url, "")
		self.assertEqual(frappe.render_template("{{ product_url('shirt') }}", {}), "/ar/products/shirt")

	def use_request(self, path):
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
		frappe.local.request = Request(EnvironBuilder(path=path).get_environ())
		frappe.local.request_cache.clear()


class TestImageUrl(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		self.path = f"/files/reads-test-{frappe.generate_hash(length=8)}.png"
		Image.new("RGBA", (800, 400), (200, 30, 30, 255)).save(frappe.get_site_path("public", self.path[1:]))
		self.addCleanup(os.remove, frappe.get_site_path("public", self.path[1:]))
		self.addCleanup(self.remove_resized_images)

	def remove_resized_images(self):
		for width in format.IMAGE_WIDTHS:
			resized_path = format.get_public_path(format.get_resized_image_url(self.path, width))
			if os.path.isfile(resized_path):
				os.remove(resized_path)

	def test_first_url_resizes_through_the_endpoint_then_links_the_webp(self):
		endpoint_url = format.image_url(self.path, 500)
		self.assertTrue(endpoint_url.startswith(format.RESIZE_ENDPOINT))
		self.assertIn("width=640", endpoint_url)

		images.get_resized_image(self.path, 640)
		resized_url = frappe.local.response["location"]
		self.assertEqual(format.image_url(self.path, 500), resized_url)
		with Image.open(frappe.get_site_path("public", resized_url[1:])) as resized:
			self.assertEqual((resized.format, resized.size), ("WEBP", (640, 320)))

	def test_a_small_image_is_never_upscaled(self):
		resized_url = format.save_resized_image(self.path, 1920)
		with Image.open(frappe.get_site_path("public", resized_url[1:])) as resized:
			self.assertEqual(resized.size, (800, 400))

	def test_other_paths_pass_through_and_bad_requests_are_refused(self):
		for path in (
			"https://cdn.example.com/a.jpg",
			"/assets/commera/a.png",
			"/files/a.svg",
			"/private/files/a.jpg",
		):
			self.assertEqual(format.image_url(path, 320), path)
		self.assertEqual(format.image_url(self.path), self.path)
		self.assertIsNone(format.image_url(None, 320))

		self.assertRaises(frappe.ValidationError, format.save_resized_image, self.path, 333)
		self.assertRaises(frappe.ValidationError, format.save_resized_image, "/private/files/a.jpg", 320)
		self.assertRaises(
			frappe.DoesNotExistError, format.save_resized_image, "/files/../../site_config.png", 320
		)
		frappe.local.message_log = []
		self.assertRaises(frappe.DoesNotExistError, format.save_resized_image, "/files/missing.png", 320)
		self.assertEqual(get_shopper_messages(), ["Image /files/missing.png not found"])
