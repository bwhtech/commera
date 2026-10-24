import re
import shutil
import tempfile
from urllib.parse import quote

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import set_request
from frappe.utils.jinja import get_jenv
from frappe.website.serve import get_response

from commera.api.admin.pages import save_page
from commera.sdk.testing import assert_theme_valid
from commera.shop_themes.chrome_preview import (
	COMMON_BLANKED_BLOCKS,
	FOOTER_BLOCKS,
	get_preview_context,
	get_preview_layout,
	render_chrome_preview,
)
from commera.shop_themes.doctype.shop_theme.shop_theme import get_theme_context, render_theme_context
from commera.shop_themes.layouts import (
	LAYOUT_CACHE_KEY,
	clear_layout_cache,
	layout_override,
	save_theme_layout,
)
from commera.shop_themes.render import render_themed_template
from commera.shop_themes.section_render import ERROR_THROTTLE_CACHE_PREFIX
from commera.shop_themes.theme_check import check_themes_on_disk
from commera.shop_themes.theme_files import get_default_layout, get_section_schemas, theme_file_cache
from commera.shop_themes.theme_resolver import ThemePageRenderer, get_theme_environment
from commera.tests import get_test_configurator

BASE_THEME = "Shop Base Theme"
BASE_SLUG = "shop_base_theme"
BASE_SECTION_TYPES = {
	"image_banner",
	"rich_text",
	"featured_collection",
	"collection_list",
	"image_with_text",
	"multicolumn",
	"main_page",
}
SECTION_TYPE_PATTERN = re.compile(r'data-section-type="([a-z_]+)"')


class IntegrationTestBaseTheme(IntegrationTestCase):
	def setUp(self):
		self.original_active_theme = frappe.db.get_single_value("Shop Theme Settings", "active_theme")
		self.original_lang = frappe.local.lang
		self.addCleanup(self.restore_site)
		self.clear_theme_caches()
		self.base_dirs = get_theme_context(BASE_THEME)["dirs"]

	def restore_site(self):
		frappe.db.rollback()
		frappe.db.set_single_value("Shop Theme Settings", "active_theme", self.original_active_theme)
		frappe.local.lang = self.original_lang
		frappe.set_user("Administrator")
		self.clear_theme_caches()

	def clear_theme_caches(self):
		frappe.clear_cache()
		theme_file_cache.clear()
		frappe.cache.delete_value(LAYOUT_CACHE_KEY)
		frappe.cache.delete_keys(f"{ERROR_THROTTLE_CACHE_PREFIX}|{BASE_THEME}")

	def activate(self, theme_name):
		frappe.db.set_single_value("Shop Theme Settings", "active_theme", theme_name)
		frappe.clear_cache()

	def get_page(self, path, lang="en"):
		frappe.local.lang = lang
		for local_key in ("jenv", "jenv_restricted", "jenv_unrestricted"):
			if hasattr(frappe.local, local_key):
				delattr(frappe.local, local_key)
		set_request(method="GET", path=path)
		response = get_response()
		return response, frappe.safe_decode(response.get_data())

	def get_base_error_logs(self):
		return frappe.get_all(
			"Error Log",
			filters={"reference_doctype": "Shop Theme", "reference_name": BASE_THEME},
			pluck="name",
		)

	def render_base(self, template_source):
		with render_theme_context(get_theme_context(BASE_THEME)):
			return render_themed_template(template_source, {}, theme_name=BASE_THEME)

	def render_base_layout(self, template, layout):
		with layout_override(template, layout):
			return self.render_base(f'{{{{ render_layout("{template}") }}}}')

	def get_published_item_group(self):
		suffix = frappe.generate_hash(length=8).upper()
		item_group = frappe.new_doc("Item Group")
		item_group.item_group_name = f"Base Theme Group {suffix}"
		item_group.parent_item_group = "All Item Groups"
		item_group.is_group = 0
		item_group.custom_displayname = item_group.item_group_name
		item_group.insert()

		item = frappe.new_doc("Item")
		item.item_code = f"BASE-THEME-{suffix}"
		item.item_name = item.item_code
		item.item_group = item_group.name
		item.stock_uom = "Nos"
		item.insert()

		variant = frappe.new_doc("Style Attribute Variant")
		variant.configurator = get_test_configurator()
		variant.item_style = item.name
		variant.item_group = item_group.name
		variant.attribute_value = f"Val {suffix}"
		variant.display_name = f"Base Theme Product {suffix}"
		variant.route = f"base-theme-{suffix.lower()}"
		variant.append("images", {"image": "/assets/base-theme-test.jpg"})
		variant.append("sizes", {"size": "M", "item_code": item.name})
		variant.is_published = 1
		variant.insert(ignore_permissions=True)
		return item_group.name

	def test_home_renders_the_default_layout_through_the_theme(self):
		self.get_published_item_group()
		self.activate(BASE_THEME)

		response, html = self.get_page("/en")

		self.assertEqual(response.status_code, 200)
		self.assertIn("theme-base", html)
		default_types = [
			section["type"] for section in get_default_layout(self.base_dirs, "index")["sections"]
		]
		self.assertEqual(SECTION_TYPE_PATTERN.findall(html), default_types)
		self.assertIn("Welcome to our store", html)
		self.assertIn("--theme-page_width: 1280px", html)

	def test_home_has_one_h1_from_the_image_banner(self):
		self.activate(BASE_THEME)

		_response, html = self.get_page("/en")

		self.assertEqual(re.findall(r"<h1\b[^>]*>([^<]*)</h1>", html), ["Welcome to our store"])

	def test_a_heading_block_prints_the_chosen_tag(self):
		block = {"id": "rich_text-heading", "type": "heading", "settings": {"heading": "Our story"}}
		layout = {"sections": [{"id": "rich_text", "type": "rich_text", "blocks": [block]}]}
		self.assertRegex(self.render_base_layout("index", layout), r"<h2 [^>]*>Our story</h2>")

		block["settings"]["heading_tag"] = "h3"
		self.assertRegex(self.render_base_layout("index", layout), r"<h3 [^>]*>Our story</h3>")

	def test_content_images_carry_the_merchants_alt_text(self):
		layout = {
			"sections": [
				{
					"id": "image_with_text",
					"type": "image_with_text",
					"settings": {"image_alt": {"en": "Linen shirts on a rail", "ar": "قمصان كتان"}},
				},
				{
					"id": "multicolumn",
					"type": "multicolumn",
					"blocks": [
						{
							"id": "column-1",
							"type": "column",
							"settings": {"image": "/files/linen.jpg", "image_alt": "A folded linen shirt"},
						}
					],
				},
			]
		}
		html = self.render_base_layout("index", layout)
		self.assertIn('alt="Linen shirts on a rail"', html)
		self.assertRegex(html, r'src="/files/linen.jpg"\s+alt="A folded linen shirt"')

	def test_home_in_arabic_is_right_to_left_with_arabic_copy(self):
		self.activate(BASE_THEME)

		response, html = self.get_page("/ar", lang="ar")

		self.assertEqual(response.status_code, 200)
		self.assertIn('<html lang="ar" dir="rtl">', html)
		self.assertIn("أهلاً بك في متجرنا", html)
		self.assertIn('href="/ar/products"', html)

	def test_store_pages_render_through_the_theme(self):
		self.activate(BASE_THEME)
		product_route = frappe.db.get_value("Style Attribute Variant", {"is_published": 1}, "route")

		for path in ("/en/products", f"/en/products/{product_route}", "/en/cart"):
			with self.subTest(path=path):
				response, html = self.get_page(path)
				self.assertEqual(response.status_code, 200)
				self.assertIn("theme-base", html)
				self.assertIn('class="page-width"', html)

	def test_checkout_is_served_by_the_theme(self):
		self.activate(BASE_THEME)
		set_request(method="GET", path="/en/cart/checkout")
		renderer = ThemePageRenderer("en/cart/checkout")

		self.assertTrue(renderer.can_render())
		self.assertEqual(renderer.template_path, "pages/cart/checkout.html")
		get_theme_environment(get_jenv(), renderer.theme_dirs).get_template(
			"theme://pages/cart/checkout.html"
		)

	def test_content_page_renders_the_main_page_section(self):
		self.activate(BASE_THEME)
		save_page(title="ZZ Base Theme Page", content="<p>base theme content</p>", route="zz-base-theme-page")

		response, html = self.get_page("/en/page/zz-base-theme-page")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(SECTION_TYPE_PATTERN.findall(html), ["main_page"])
		self.assertIn("ZZ Base Theme Page</h1>", html)
		self.assertIn("<p>base theme content</p>", html)

	def test_missing_content_page_renders_not_found(self):
		self.activate(BASE_THEME)

		_response, html = self.get_page("/en/page/zz-no-such-page")

		self.assertEqual(SECTION_TYPE_PATTERN.findall(html), ["main_page"])
		self.assertIn("Page not found", html)

	def test_every_section_renders_alone_with_its_defaults(self):
		self.get_published_item_group()
		schemas = get_section_schemas(self.base_dirs)
		self.assertEqual(set(schemas), BASE_SECTION_TYPES)
		errors_before = self.get_base_error_logs()

		for section_type, schema in schemas.items():
			preset = (schema.get("presets") or [{}])[0]
			blocks = [
				{"id": f"{section_type}-{index}", "type": block_type, "settings": {}}
				for index, block_type in enumerate(preset.get("blocks") or [], start=1)
			]
			layout = {
				"sections": [{"id": section_type, "type": section_type, "settings": {}, "blocks": blocks}]
			}
			template = "page" if section_type == "main_page" else "index"
			with self.subTest(section_type=section_type):
				html = self.render_base_layout(template, layout)
				self.assertNotIn("data-section-error", html)
				self.assertNotIn("{{", html)
				if section_type != "collection_list":
					self.assertEqual(SECTION_TYPE_PATTERN.findall(html), [section_type])

		self.assertEqual(self.get_base_error_logs(), errors_before)

	def test_collection_list_links_each_collection_to_its_listing(self):
		item_group = self.get_published_item_group()
		layout = {
			"sections": [
				{
					"id": "collection_list",
					"type": "collection_list",
					"blocks": [
						{
							"id": "first",
							"type": "featured_collection",
							"settings": {"collection": item_group},
						},
						{
							"id": "missing",
							"type": "featured_collection",
							"settings": {"collection": "ZZ Gone"},
						},
					],
				}
			]
		}

		html = self.render_base_layout("index", layout)

		self.assertEqual(SECTION_TYPE_PATTERN.findall(html), ["collection_list"])
		self.assertEqual(html.count('class="group flex flex-col gap-3"'), 1)
		self.assertIn(f"subcategory={quote(item_group)}", html)

	def test_featured_collection_shows_only_that_collection(self):
		item_group = self.get_published_item_group()
		layout = {
			"sections": [
				{
					"id": "featured_collection",
					"type": "featured_collection",
					"settings": {"collection": item_group, "products_to_show": 2},
				}
			]
		}

		html = self.render_base_layout("index", layout)

		product_routes = re.findall(r'href="/en/products/([^"]+)" class="block"', html)
		self.assertTrue(product_routes)
		self.assertLessEqual(len(product_routes), 2)
		groups = set(
			frappe.get_all(
				"Style Attribute Variant", filters={"route": ["in", product_routes]}, pluck="item_group"
			)
		)
		self.assertEqual(groups, {item_group})
		self.assertIn("subcategory=", html)

	def test_saved_theme_settings_reach_the_page_as_css_variables(self):
		self.addCleanup(clear_layout_cache, BASE_THEME, "settings")
		save_theme_layout(
			BASE_THEME, "settings", {"settings": {"accent": "#123456", "radius": 4}}, publish=True
		)

		html = self.render_base("{{ format_theme_settings_css() }}")

		self.assertIn("--theme-accent: #123456;", html)
		self.assertIn("--theme-radius: 4px;", html)

	def test_a_child_theme_with_no_files_of_its_own_renders_the_base_store(self):
		child_dir = tempfile.mkdtemp(prefix="commera_base_child_")
		self.addCleanup(shutil.rmtree, child_dir)
		child_context = {
			"theme_name": "ZZ Base Child",
			"names": ["ZZ Base Child", BASE_THEME],
			"dirs": [child_dir, *self.base_dirs],
			"apps": {"ZZ Base Child": "commera", BASE_THEME: "commera"},
			"settings_doctype": None,
		}

		with render_theme_context(child_context):
			home_response, home_html = self.get_page("/en")
			list_response, list_html = self.get_page("/en/products")

		self.assertEqual(home_response.status_code, 200)
		self.assertIn('data-section-type="image_banner"', home_html)
		self.assertEqual(list_response.status_code, 200)
		self.assertIn("theme-base", list_html)

	def test_base_theme_has_no_check_findings(self):
		assert_theme_valid(BASE_SLUG)
		self.assertEqual(check_themes_on_disk(BASE_SLUG), [])

	def test_chrome_preview_uses_each_themes_own_layout(self):
		preview_context = get_preview_context(frappe.get_cached_doc("Commera Settings"), "en")

		self.activate("Shop Default Theme")
		self.assertEqual(
			get_preview_layout(get_theme_context("Shop Default Theme")), "components/theme_layout.html"
		)
		default_preview = render_chrome_preview(preview_context, COMMON_BLANKED_BLOCKS + FOOTER_BLOCKS)
		self.assertIn('data-shop-theme="shop_default_theme"', default_preview)

		self.activate(BASE_THEME)
		base_preview = render_chrome_preview(preview_context, COMMON_BLANKED_BLOCKS + FOOTER_BLOCKS)
		self.assertIn("theme-base", base_preview)
		self.assertIn("<nav", base_preview)
		self.assertNotIn("<footer", base_preview)
