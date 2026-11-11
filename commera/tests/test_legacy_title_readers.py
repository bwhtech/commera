"""Legacy pages, the summer theme and search read product titles from Content Translation."""

import json

import frappe
from frappe.website.serve import get_response_content
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera import utils
from commera.api.admin.theme import activate_theme
from commera.localization import register
from commera.localization.routing import localize_request
from commera.search import record_builder
from commera.search.remote_engine import product_document
from commera.tests.test_content_translation import use_storefront_language
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_product_details import ProductDetailPriceTestCase
from commera.www.account.orders.index import add_line_titles
from commera.www.cart import permalink
from commera.www.products import details

PRODUCT = "Style Attribute Variant"
ARABIC_TITLE = "قميص & كتان"
ARABIC_DESCRIPTION = "<p>قميص كتان للأيام الدافئة.</p>"


class TestLegacyTitleReaders(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		use_storefront_languages(self, "en", published=("en", "ar"))
		self.route = self.make_priced_variant("LEGACY", default_rate=30)
		self.product = frappe.get_doc(PRODUCT, {"route": self.route})
		self.item_code = self.product.sizes[0].item_code
		register(PRODUCT, self.product.name, "display_name", "ar", ARABIC_TITLE)
		register(PRODUCT, self.product.name, "description", "ar", ARABIC_DESCRIPTION)

	def test_grid_cards_carry_the_title_in_the_request_language(self):
		use_storefront_language(self, "ar")
		self.assertEqual(self.card()["title"], ARABIC_TITLE)
		use_storefront_language(self, "en")
		self.assertEqual(self.card()["title"], self.product.display_name)

	def test_the_product_page_context_has_the_arabic_title_and_description(self):
		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
		frappe.local.form_dict = frappe._dict(route=self.route, _lang="ar")
		frappe.local.request_cache.clear()
		context = frappe._dict()
		details.get_context(context)

		self.assertEqual(context.product_title, ARABIC_TITLE)
		self.assertEqual(context.product_description, ARABIC_DESCRIPTION)
		self.assertTrue(context.selected_item["title"].startswith(ARABIC_TITLE))

	def test_cart_link_and_order_lines_carry_the_arabic_title(self):
		frappe.get_doc(
			{"doctype": "Bin", "item_code": self.item_code, "warehouse": self.warehouse, "actual_qty": 5}
		).insert(ignore_permissions=True)
		order = frappe._dict(
			name="SO-LEGACY", items=json.dumps([{"item_code": self.item_code, "item_name": "x"}])
		)
		use_storefront_language(self, "ar")

		[line] = permalink.get_cart_lines({self.item_code: 1}, [])
		add_line_titles([order])

		self.assertTrue(line["variant"]["title"].startswith(ARABIC_TITLE))
		self.assertEqual(json.loads(order["items"])[0]["title"], ARABIC_TITLE)

	def test_remote_engines_take_the_arabic_title_from_content_translation(self):
		[record] = record_builder.build_product_search_records([self.product.name])
		self.assertEqual(product_document(record)["title_ar"], ARABIC_TITLE)

		frappe.db.delete("Content Translation", {"reference_name": self.product.name, "language": "ar"})
		[record] = record_builder.build_product_search_records([self.product.name])
		self.assertEqual(product_document(record)["title_ar"], "")

	def test_the_summer_and_legacy_product_pages_show_the_arabic_title_escaped(self):
		for theme in ("Summer Theme", "Shop Default Theme"):
			with self.subTest(theme):
				activate_theme(theme)
				html = render_page(self, f"/ar/products/{self.route}")
				self.assertIn("قميص &amp; كتان", html)
				self.assertIn(ARABIC_DESCRIPTION, html)
				# frappe_call asks the server for replies in the page's language.
				self.assertIn('const page_language = "ar";', html)
				english = render_page(self, f"/products/{self.route}")
				self.assertIn(self.product.display_name, english)
				self.assertIn("const page_language = null;", english)

	def card(self):
		return utils.get_product_list(product_list=[self.product.name], page_length=1)[0]


def render_page(test, path):
	"""The HTML a guest gets for `path`, routed and localized as a real request."""
	test.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
	test.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
	test.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
	test.addCleanup(frappe.clear_cache)
	frappe.local.request = Request(EnvironBuilder(path=path).get_environ())
	frappe.local.form_dict = frappe._dict()
	frappe.local.request_cache.clear()
	frappe.set_user("Guest")
	try:
		localize_request()
		return get_response_content(frappe.local.request.path)
	finally:
		frappe.set_user("Administrator")
