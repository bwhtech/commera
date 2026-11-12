"""Merchant content keeps its own direction on any page: blocks get dir="auto", inline values a <bdi>."""

import re

import frappe

from commera.api.admin.theme import activate_theme
from commera.tests.test_legacy_title_readers import render_page
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_product_details import ProductDetailPriceTestCase

PRODUCT = "Style Attribute Variant"
ENGLISH = {
	"title": "This PREMIUM snowboard.",
	"description": "Made to be lived in.",
	"sizes": ("M (Medium)", "XL."),
}
ARABIC = {"title": "لوح تزلج فاخر.", "description": "مصنوع ليُعاش فيه.", "sizes": ("صغير (S)", "كبير.")}


class TestRtlMerchantContent(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		use_storefront_languages(self, "en", published=("en", "ar"))

	def test_english_content_on_the_arabic_starter_page_is_isolated(self):
		self.assert_starter_page("/ar", self.make_product("RTLEN", ENGLISH), ENGLISH)

	def test_arabic_content_on_the_english_starter_page_is_isolated(self):
		self.assert_starter_page("", self.make_product("RTLAR", ARABIC), ARABIC)

	def test_the_starter_cart_isolates_line_titles_and_sizes(self):
		activate_theme("Commera Starter")
		html = render_page(self, "/ar/cart")
		self.assertIn('<bdi x-text="line.product?.title ?? line.title"></bdi>', html)
		self.assertIn('<bdi x-text="line.product?.variant_title"></bdi>', html)

	def test_the_summer_page_isolates_english_content(self):
		route = self.make_product("RTLSUMMER", ENGLISH)
		activate_theme("Summer Theme")
		html = render_page(self, f"/ar/products/{route}")
		self.assertRegex(html, block_with(r'<p dir="auto" class="para-text">', ENGLISH["description"]))
		self.assertRegex(html, rf"<h1 [^>]*>\s*<bdi>{re.escape(ENGLISH['title'])}</bdi>")
		for size in ENGLISH["sizes"]:
			self.assertIn(f"><bdi>{size}</bdi></label>", html)

	def test_the_legacy_page_isolates_english_content(self):
		route = self.make_product("RTLLEGACY", ENGLISH)
		activate_theme("Shop Default Theme")
		html = render_page(self, f"/ar/products/{route}")
		self.assertRegex(html, block_with(r'<div dir="auto">', ENGLISH["description"]))
		self.assertRegex(html, rf"<bdi>{re.escape(ENGLISH['title'].title())}</bdi>")
		for size in ENGLISH["sizes"]:
			self.assertRegex(html, rf"<button\b[^>]*>\s*<bdi>{re.escape(size)}</bdi>")

	def assert_starter_page(self, prefix, route, content):
		activate_theme("Commera Starter")
		html = render_page(self, f"{prefix}/products/{route}")
		title = content["title"]
		self.assertRegex(html, block_with(r'<div dir="auto" class="rich-text[^"]*">', content["description"]))
		self.assertIn(f'md:text-7xl"><bdi>{title}</bdi></h1>', html)
		self.assertIn(f'<bdi aria-current="page">{title}</bdi>', html)
		for size in content["sizes"]:
			self.assertIn(f'class="chip"><bdi>{size}</bdi></button>', html)

	def make_product(self, label, content):
		"""A published product in two sizes, each its own priced item."""
		route = self.make_priced_variant(label, default_rate=30)
		product = frappe.get_doc(PRODUCT, {"route": route})
		second_size = self.make_item(f"{label}-2")
		self.make_item_price(second_size, self.default_price_list, 30)
		product.sizes[0].size = content["sizes"][0]
		product.append("sizes", {"size": content["sizes"][1], "item_code": second_size})
		product.display_name = content["title"]
		product.save(ignore_permissions=True)
		frappe.db.set_value("Item", product.item_style, "description", f"<p>{content['description']}</p>")
		return route


def block_with(opening_tag, text):
	"""A block opening tag that holds the paragraph `text`."""
	return rf"{opening_tag}\s*<p>{re.escape(text)}</p>"
