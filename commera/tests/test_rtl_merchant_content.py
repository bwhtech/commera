"""Merchant content keeps its own direction on any page: blocks get dir="auto", inline values a <bdi>."""

import re
from pathlib import Path
from types import SimpleNamespace

import frappe
import html5lib
from jinja2 import Environment

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
		self.assert_description_descendants(html, ENGLISH["description"], expected=2)
		self.assertRegex(html, rf"<h1 [^>]*>\s*<bdi>{re.escape(ENGLISH['title'])}</bdi>")
		for size in ENGLISH["sizes"]:
			self.assertIn(f"><bdi>{size}</bdi></label>", html)

	def test_the_summer_collection_heading_is_isolated_and_escaped(self):
		html = render_value_lines(
			"themes/summer_theme/pages/products/list.html", ["<h1>"], category="Shirts & co (Summer)."
		)
		self.assertIn("<h1><bdi>Shirts &amp; co (Summer).</bdi></h1>", html)

	def test_the_legacy_page_isolates_english_content(self):
		route = self.make_product("RTLLEGACY", ENGLISH)
		activate_theme("Shop Default Theme")
		html = render_page(self, f"/ar/products/{route}")
		self.assert_description_descendants(html, ENGLISH["description"])
		self.assertRegex(html, rf"<bdi>{re.escape(ENGLISH['title'].title())}</bdi>")
		for size in ENGLISH["sizes"]:
			self.assertRegex(html, rf"<button\b[^>]*>\s*<bdi>{re.escape(size)}</bdi>")

	def test_summer_filters_isolate_values_and_keep_category_escaping(self):
		from frappe.utils.jinja import get_jenv

		from commera.shop_themes.theme_resolver import get_theme_environment

		directory = Path(frappe.get_app_path("commera", "themes", "summer_theme"))
		environment = get_theme_environment(get_jenv(), [str(directory)])
		node = frappe._dict(display_name="قمصان & Shirts.", is_leaf=True, item_groups=["Shirts"])
		context = {
			"filters": {"colors": ["Blue."], "sizes": ["صغير (S)"], "brands": ["Brand."], "Category": [node]},
			"swatches": {},
		}
		html = environment.get_template("theme://components/sections/shop_filter_sidebar.html").render(
			context
		)
		tree = html5lib.parse(html, namespaceHTMLElements=False)
		values = [element.text for element in tree.iter("bdi")]
		for value in ("Blue.", "صغير (S)", "Brand.", node.display_name, "Category"):
			self.assertIn(value, values)
		self.assertIn("قمصان &amp; Shirts.", html)

	def test_summer_order_sizes_and_brand_are_isolated(self):
		html = render_value_lines(
			"themes/summer_theme/pages/account/orders/detail.html",
			("{{ item.size }}", "{{ item.brand }}"),
			item=frappe._dict(size="صغير (S)", brand="Brand."),
		)
		tree = html5lib.parse(html, namespaceHTMLElements=False)
		self.assertEqual([element.text for element in tree.iter("bdi")], ["صغير (S)", "Brand.", "صغير (S)"])

	def test_summer_colour_labels_keep_the_styled_span(self):
		html = render_value_lines(
			"themes/summer_theme/components/sections/product_info.html",
			("{{ product_variant.attribute_value }}", "{{ variant.attribute_value }}"),
			product_variant=frappe._dict(attribute_value="Blue."),
			variant=frappe._dict(attribute_value="أحمر."),
			images=["/test.jpg"],
		)
		tree = html5lib.parse(html, namespaceHTMLElements=False)
		self.assertEqual([element.text for element in tree.findall(".//span/bdi")], ["Blue.", "أحمر."])

	def test_legacy_checkout_values_are_isolated_and_title_stays_escaped(self):
		html = render_value_lines(
			"templates/components/checkout_product_details.html",
			("cart_item.brand", "cart_item.title", "cart_item.size"),
			cart_item=frappe._dict(brand="Brand.", title="Shirt & linen.", size="صغير (S)"),
		)
		tree = html5lib.parse(html, namespaceHTMLElements=False)
		self.assertEqual(
			[element.text for element in tree.iter("bdi")], ["Brand.", "Shirt & linen.", "صغير (S)"]
		)
		self.assertIn("Shirt &amp; linen.", html)

	def test_legacy_filter_and_cart_alpine_values_keep_styled_elements(self):
		for template in (
			"templates/components/product_filter.html",
			"templates/components/cart_product_size_dropdown.html",
			"templates/components/cart_dropdown.html",
			"templates/macros/search_bar_modal.html",
			"templates/macros/search_combo_box.html",
		):
			with self.subTest(template=template):
				source = Path(frappe.get_app_path("commera", template)).read_text()
				markup = [
					match.group()
					for match in re.finditer(
						r"<(span|label|p|h6)\b[^>]*>\s*(?:<bdi\b[^>]*>\s*</bdi>)?\s*</\1>", source
					)
					if "x-text" in match.group()
				]
				self.assertTrue(markup)
				html = template_environment().from_string("".join(markup)).render()
				tree = html5lib.parse(html, namespaceHTMLElements=False)
				isolated = []
				for element in tree.iter():
					expression = element.get("x-text", "")
					if re.search(
						r"brand|title|item_name|size|display_name|option|item.label|format_key|attribute_value|item_group|category.label",
						expression,
					):
						self.assertEqual(element.tag, "bdi", expression)
						isolated.append(expression)
				self.assertTrue(isolated)

	def test_legacy_dashboard_line_values_keep_escaping_and_isolation(self):
		source = Path(
			frappe.get_app_path("commera", "templates/macros/user_dashboard_product.html")
		).read_text()
		environment = template_environment()
		html = environment.from_string(
			source + '{{ dashboard_product("", "Brand.", "Shirt & linen.", 30, size="صغير (S)") }}'
		).render()
		tree = html5lib.parse(html, namespaceHTMLElements=False)
		self.assertEqual(
			[element.text for element in tree.iter("bdi")], ["Brand.", "Shirt & linen.", "صغير (S)"]
		)
		self.assertIn("Shirt &amp; linen.", html)

	def test_summer_metadata_keeps_escaping_and_inline_isolation(self):
		html = render_value_lines(
			"themes/summer_theme/components/sections/product_info.html",
			("{{ selected_item.item_code", "{{ product_variant.item_group", "{{ selected_item.material"),
			selected_item=frappe._dict(item_code="SKU & 42.", material="قطن (Cotton)."),
			product_variant=frappe._dict(item_group="Shirts & tops."),
			url=lambda value: value,
		)
		tree = html5lib.parse(html, namespaceHTMLElements=False)
		self.assertEqual(
			[element.text for element in tree.iter("bdi")],
			["SKU & 42.", "Shirts & tops.", "قطن (Cotton)."],
		)
		self.assertIn("SKU &amp; 42.", html)
		self.assertEqual(len(tree.findall(".//a/bdi")), 1)

	def test_selected_filter_chip_keeps_its_label_isolated_and_escaped(self):
		html = render_value_lines(
			"themes/commera_starter/components/product_grid.html",
			("{{ chip.label",),
			chip=frappe._dict(url="/products", label="Size & مقاس (M)."),
			icon=lambda *args: "",
		)
		tree = html5lib.parse(html, namespaceHTMLElements=False)
		self.assertEqual(tree.find(".//a/span/bdi").text, "Size & مقاس (M).")
		self.assertIn("Size &amp; مقاس (M).", html)

	def test_swept_jinja_labels_keep_escaping_and_isolation(self):
		cases = (
			("themes/commera_starter/sections/header.html", 'item["title"]'),
			("themes/commera_starter/components/macros/menu_link.html", 'item["title"]'),
			("themes/commera_starter/sections/footer.html", "shop_name"),
			("themes/commera_starter/sections/hero.html", "section.settings.primary_label"),
			("themes/summer_theme/components/macros/navigation.html", "node.label"),
			("themes/summer_theme/sections/collection.html", "banner.settings.heading"),
			("themes/summer_theme/sections/hero_slider.html", "slide.settings.heading"),
			("themes/summer_theme/sections/recent_additions.html", "product_name"),
			("themes/summer_theme/sections/sponsored_brands.html", "brand.name"),
			("themes/summer_theme/pages/account/address.html", "address.address_line1"),
			("themes/summer_theme/components/sections/product_tabs.html", "product_variant.attribute_name"),
			("templates/macros/navigation_menu.html", "text"),
			("themes/summer_theme/pages/account/orders/detail.html", "tax.description"),
			("themes/summer_theme/pages/account/orders/detail.html", "fee.description"),
			("themes/commera_starter/pages/account/orders/detail.html", "label"),
			("templates/includes/footer.html", "link.title"),
			("www/account/address.html", "address.display"),
		)
		for template, expression in cases:
			with self.subTest(template=template, expression=expression):
				source = Path(frappe.get_app_path("commera", template)).read_text()
				pattern = r"<bdi>\s*{{\s*" + re.escape(expression) + r"\s*\|\s*e\s*}}\s*</bdi>"
				matches = re.findall(pattern, source)
				self.assertTrue(matches)
				markup = re.sub(r"{{.*?}}", "{{ value | e }}", matches[0])
				html = Environment().from_string(markup).render(value="Shirts & قمصان (M).")
				tree = html5lib.parse(html, namespaceHTMLElements=False)
				self.assertEqual(tree.find(".//bdi").text, "Shirts & قمصان (M).")
				self.assertIn("&amp;", html)

	def test_swept_alpine_values_are_isolated_in_parsed_markup(self):
		roots = ("themes/commera_starter", "themes/summer_theme", "templates", "www")
		merchant_value = re.compile(
			r"attribute_value|item_group|category.label|chip.label|get_product_name|"
			r"item.brand|item.title|item.item_name|item.display|selectedOption.*display|"
			r"option.label|method.title|tax.description|fee.description|discount.label|"
			r"discount.code|code_state.code|selected_shipping_option|gateway_name|"
			r"details\?\.payment_mode|cell \?\?|cell \|\|"
		)
		for root in roots:
			for template in Path(frappe.get_app_path("commera", root)).rglob("*.html"):
				source = re.sub(r"{%.*?%}", "", template.read_text(), flags=re.S)
				source = re.sub(r"{{.*?}}", "value", source, flags=re.S)
				tree = html5lib.parse(source, namespaceHTMLElements=False)
				for element in tree.iter():
					expression = element.get("x-text", "")
					if merchant_value.search(expression) and not expression.startswith("$el.dataset.message"):
						with self.subTest(template=str(template), expression=expression):
							self.assertEqual(element.tag, "bdi")

	def assert_description_descendants(self, html, description, expected=1):
		tree = html5lib.parse(html, namespaceHTMLElements=False)
		paragraphs = [
			paragraph
			for element in tree.iter()
			if element.get("dir") == "auto"
			for paragraph in element.iter("p")
			if "".join(paragraph.itertext()) == description
		]
		self.assertEqual(len(paragraphs), expected)

	def assert_starter_page(self, prefix, route, content):
		activate_theme("Commera Starter")
		html = render_page(self, f"{prefix}/products/{route}")
		title = content["title"]
		self.assert_description_descendants(html, content["description"])
		self.assertIn(f'md:text-7xl"><bdi>{title}</bdi></h1>', html)
		self.assertIn(f'<span aria-current="page"><bdi>{title}</bdi></span>', html)
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


def render_value_lines(template, expressions, **context):
	"""Render the actual value markup without unrelated page dependencies."""
	source = Path(frappe.get_app_path("commera", template)).read_text()
	lines = [line for line in source.splitlines() if any(value in line for value in expressions)]
	environment = Environment()
	environment.globals["_"] = lambda value: value
	environment.globals.update({key: value for key, value in context.items() if callable(value)})
	return environment.from_string("\n".join(lines)).render(context)


def template_environment():
	environment = Environment()
	currency = SimpleNamespace(symbol="$", precision=2, config={"precision": 2}, amount="{:.2f}".format)
	environment.globals.update(
		_=lambda value: value, get_currency_symbol=lambda: "$", get_cart_currency=lambda *args: currency
	)
	return environment
