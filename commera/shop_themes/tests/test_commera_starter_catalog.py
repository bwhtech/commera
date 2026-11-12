import os
from unittest.mock import patch

import frappe
import html5lib
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

import commera.sdk
from commera.shop_themes.doctype.shop_theme.shop_theme import render_theme_context
from commera.shop_themes.sections import get_theme_json, validate_layout
from commera.shop_themes.theme_resolver import ThemePageRenderer
from commera.tests.test_localization import use_storefront_languages

STARTER = "Commera Starter"
STARTER_DIR = os.path.join(frappe.get_app_path("commera"), "themes", "commera_starter")
CATALOG_LAYOUTS = {
	"products": "main_collection",
	"search": "main_search",
	"product": "main_product",
	"page": "main_page",
}


class IntegrationTestCommeraStarterCatalog(IntegrationTestCase):
	def setUp(self):
		self.theme_context = {
			"theme_name": STARTER,
			"theme_type": "Sections",
			"names": [STARTER],
			"dirs": [STARTER_DIR],
			"apps": {STARTER: "commera"},
			"settings_doctype": None,
		}
		frappe.db.delete("Theme Layout", {"theme": STARTER})

		self.saved_request = getattr(frappe.local, "request", None)
		self.saved_form_dict = frappe.local.form_dict
		self.saved_lang = frappe.local.lang
		self.addCleanup(self.restore_locals)
		frappe.local.lang = "en"

	def restore_locals(self):
		frappe.local.request = self.saved_request
		frappe.local.form_dict = self.saved_form_dict
		frappe.local.lang = self.saved_lang

	def render(self, template_path, path, **form):
		frappe.local.request = Request(EnvironBuilder(path=path).get_environ())
		frappe.local.form_dict = frappe._dict(form)
		with render_theme_context(self.theme_context):
			renderer = ThemePageRenderer(path.strip("/"))
			renderer.theme_dirs = [STARTER_DIR]
			renderer.template_path = template_path
			response = renderer.render()
		return response.status_code, response.get_data(as_text=True)

	def get_any_product(self):
		products = commera.sdk.catalog.list_products(page_size=1)["products"]
		if not products:
			self.skipTest("The site has no published products.")
		return products[0]

	def test_every_catalog_layout_passes_the_layout_checks_and_holds_its_main_section(self):
		for page, main_section in CATALOG_LAYOUTS.items():
			with self.subTest(page):
				layout = get_theme_json([STARTER_DIR], f"layouts/{page}.json")
				validate_layout(self.theme_context, layout, page)
				self.assertEqual(layout["sections"][0]["type"], main_section)

	def test_a_main_section_is_refused_outside_its_page(self):
		for page, main_section in CATALOG_LAYOUTS.items():
			with self.subTest(page), self.assertRaises(frappe.ValidationError):
				validate_layout(
					self.theme_context, {"sections": [{"id": "probe", "type": main_section}]}, "index"
				)

		with self.assertRaises(frappe.ValidationError):
			validate_layout(
				self.theme_context, {"sections": [{"id": "probe", "type": "product_recommendations"}]}, "page"
			)

	def test_a_page_layout_is_refused_without_its_main_section(self):
		for page, main_section in CATALOG_LAYOUTS.items():
			with self.subTest(page):
				with self.assertRaises(frappe.ValidationError):
					validate_layout(self.theme_context, {"sections": []}, page)
				with self.assertRaises(frappe.ValidationError):
					validate_layout(
						self.theme_context,
						{"sections": [{"id": "main", "type": main_section, "hidden": True}]},
						page,
					)
				validate_layout(
					self.theme_context, {"sections": [{"id": "main", "type": main_section}]}, page
				)

	def test_the_listing_shows_published_products_with_filters_and_sorting(self):
		product = self.get_any_product()

		status, html = self.render("pages/products/list.html", "/en/products")

		self.assertEqual(status, 200)
		self.assertIn("All products", html)
		self.assertIn('id="listing-filters"', html)
		self.assertIn('name="sort_by"', html)
		self.assertIn(commera.sdk.format.product_url(product["handle"]), html)

	def test_a_category_link_lists_that_collection(self):
		collections = commera.sdk.catalog.list_collections()
		if not collections:
			self.skipTest("The site has no collections.")
		collection = collections[0]

		status, html = self.render("pages/products/list.html", "/en/products", category=collection["handle"])

		self.assertEqual(status, 200)
		self.assertIn(f"><bdi>{collection['title']}</bdi></h1>", html)
		self.assertIn(f'name="category" value="{collection["handle"]}"', html)

	def test_a_collection_page_shows_its_description(self):
		category = frappe.get_doc(
			{
				"doctype": "Ecommerce Category",
				"category_name": f"Described {frappe.generate_hash(length=8)}",
				"description": "Linen <b>for</b> summer",
				"enabled": 1,
			}
		).insert(ignore_permissions=True)
		# The menu is memoised per request; an earlier test may have built it without this tab.
		frappe.local.commera_storefront_menu = None

		status, html = self.render("pages/products/list.html", "/en/products", category=category.route_slug)

		self.assertEqual(status, 200)
		self.assertIn("Linen &lt;b&gt;for&lt;/b&gt; summer</p>", html)

	def test_a_selected_filter_shows_as_a_chip_that_removes_it(self):
		self.get_any_product()
		use_storefront_languages(self, "en", published=("en", "ar"))

		status, html = self.render("pages/products/list.html", "/ar/products", sizes="ZZ-NO-SIZE")

		self.assertEqual(status, 200)
		self.assertIn("No products match these filters", html)
		self.assertIn('aria-label="Remove ZZ-NO-SIZE"', html)
		self.assertIn('href="/ar/products"', html)

	def test_a_search_shows_its_results_and_is_kept_out_of_search_engines(self):
		product = self.get_any_product()

		status, html = self.render(
			"pages/products/list.html", "/en/products", search=product["title"].split()[0]
		)

		self.assertEqual(status, 200)
		self.assertIn("Results for", html)
		self.assertIn("noindex", html)
		self.assertNotIn("All products", html)

	def test_a_search_with_no_results_offers_the_search_form(self):
		status, html = self.render("pages/products/list.html", "/en/products", search="zzqqxx-no-match")

		self.assertEqual(status, 200)
		self.assertIn("Nothing matches your search.", html)
		self.assertIn('value="zzqqxx-no-match"', html)

	def test_the_product_page_renders_the_product_form_and_recommendations(self):
		handle = self.get_any_product()["handle"]
		product = commera.sdk.catalog.get_product(handle)

		status, html = self.render("pages/products/details.html", f"/en/products/{handle}", route=handle)

		self.assertEqual(status, 200)
		self.assertIn(f"><bdi>{product['title']}</bdi></h1>", html.replace("&#39;", "'"))
		self.assertIn("product_form(", html)
		self.assertIn("Add to cart", html)
		self.assertIn("Shipping &amp; returns", html)
		self.assertIn('"@type": "Product"', html)

	def test_the_size_picker_selects_by_source_value_not_translated_title(self):
		# Two sizes can share a translated title, so the title must not pick the item code.
		with open(os.path.join(STARTER_DIR, "sections", "main_product.html")) as template:
			source = template.read()

		self.assertIn('@click="size = variants[{{ loop.index0 }}].size"', source)
		self.assertIn('"size": variant.size if size_option', source)
		self.assertNotIn("].title", source)

	def test_an_unknown_product_renders_the_theme_404(self):
		status, html = self.render(
			"pages/products/details.html", "/en/products/zz-no-such-product", route="zz-no-such-product"
		)

		self.assertEqual(status, 404)
		self.assertIn("Page not found", html)
		self.assertIn('name="search"', html)

	def test_the_content_page_renders_the_published_page(self):
		page = frappe.new_doc("Shop Web Page")
		page.name = "ZZ Starter Returns"
		page.route = "zz-starter-returns"
		page.content = "<p>ZZ starter returns body</p>"
		page.published = 1
		page.insert()

		status, html = self.render(
			"pages/shop_web_page.html", "/en/page/zz-starter-returns", route=page.route
		)

		self.assertEqual(status, 200)
		self.assertIn("ZZ Starter Returns</bdi></h1>", html)
		self.assertIn("ZZ starter returns body", html)

	def test_the_cart_page_and_the_drawer_share_the_cart_contents(self):
		status, html = self.render("pages/cart/cart.html", "/en/cart")

		self.assertEqual(status, 200)
		self.assertEqual(html.count("Your cart is empty<"), 2)
		self.assertEqual(html.count("$store.cart.checkout()"), 2)
		self.assertIn('x-data="order_summary"', html)
		self.assertIn('id="discount-code"', html)
		self.assertIn("noindex", html)

	def test_price_chip_translations_are_escaped_before_adding_money_html(self):
		from commera.shop_themes.theme_resolver import load_page_controller

		listing = load_page_controller([STARTER_DIR], "pages/products/list.html")

		payload = "<img src=x onerror=alert(1)>"
		for values, message in (
			({"min": 10}, "From {0}"),
			({"max": 20}, "Up to {0}"),
			({"min": 10, "max": 20}, "{0} to {1}"),
		):
			with (
				self.subTest(message=message),
				patch.object(
					listing, "_", side_effect=lambda text: payload + " " + text if text == message else text
				),
			):
				status, html = self.render("pages/products/list.html", "/products", **values)
				self.assertEqual(status, 200)
				tree = html5lib.parse(html, namespaceHTMLElements=False)
				self.assertFalse([node for node in tree.iter("img") if node.get("src") == "x"])
				self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)

	def test_url_filter_values_stay_text_in_chips_and_aria_labels(self):
		payload = "<img src=x onerror=alert(1)>"
		status, html = self.render("pages/products/list.html", "/products", colors=payload)
		self.assertEqual(status, 200)
		tree = html5lib.parse(html, namespaceHTMLElements=False)
		chips = [node for node in tree.iter("a") if node.get("aria-label") == f"Remove {payload}"]
		self.assertEqual(len(chips), 1)
		self.assertIn(payload, "".join(chips[0].itertext()))
		self.assertFalse(list(chips[0].iter("img")))
		self.assertFalse([node for node in tree.iter() if node.get("src") == "x"])
