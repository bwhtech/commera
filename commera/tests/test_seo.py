# Copyright (c) 2026, ivend and Contributors
# Tests for the pure SEO helpers (commera/seo.py) and the sitemap
# controller (commera/www/sitemap.py). Real-DB, auto-rolled-back.

import unittest

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from commera import seo, website_context
from commera.tests import get_test_configurator, get_test_item
from commera.www import sitemap, sitemap_segment

SEO_SETTING_FIELDS = (
	"store_name",
	"seo_title_template",
	"default_meta_description",
	"default_share_image",
	"favicon",
)

PAGE_SEO_KEYS = {
	"title",
	"description",
	"image",
	"url",
	"type",
	"alternates",
	"price",
	"currency",
	"availability",
	"noindex",
}


def set_seo_settings(**values):
	"""Write Commera Settings fields and bust the cached doc the SEO helpers read through."""
	for field in SEO_SETTING_FIELDS:
		frappe.db.set_single_value("Commera Settings", field, values.get(field, ""))
	frappe.clear_document_cache("Commera Settings", "Commera Settings")


class TestApplyTitleTemplate(IntegrationTestCase):
	def setUp(self):
		set_seo_settings(store_name="MyStore", seo_title_template="{title} | {store}")

	def test_formats_title_and_store(self):
		self.assertEqual(seo.apply_title_template("Running Shoes"), "Running Shoes | MyStore")

	def test_titleless_returns_store_name(self):
		self.assertEqual(seo.apply_title_template(), "MyStore")
		self.assertEqual(seo.apply_title_template(""), "MyStore")

	def test_unknown_placeholder_does_not_raise(self):
		# Fixed defect: an admin template with a stray placeholder must not KeyError/500 the storefront.
		set_seo_settings(store_name="MyStore", seo_title_template="{brand} | {store}")
		result = seo.apply_title_template("Running Shoes")
		self.assertIsInstance(result, str)
		self.assertIn("MyStore", result)
		# the unknown {brand} resolves to "" via BlankDefaultMap, not an exception
		self.assertEqual(result, " | MyStore")

	def test_custom_template_layout(self):
		set_seo_settings(store_name="MyStore", seo_title_template="{store} :: {title}")
		self.assertEqual(seo.apply_title_template("Hat"), "MyStore :: Hat")


class TestTruncateDescription(UnitTestCase):
	def test_short_string_untouched(self):
		self.assertEqual(seo.truncate_description("A short description."), "A short description.")

	def test_strips_html_and_collapses_whitespace(self):
		raw = "<p>Hello   <b>World</b></p>\n\t  foo"
		self.assertEqual(seo.truncate_description(raw), "Hello World foo")

	def test_empty_and_none(self):
		self.assertEqual(seo.truncate_description(None), "")
		self.assertEqual(seo.truncate_description(""), "")

	def test_clamps_on_word_boundary_with_ellipsis(self):
		clean = " ".join(["word"] * 60)  # 60 * 5 - 1 = 299 chars, well over 160
		result = seo.truncate_description(clean)
		self.assertLessEqual(len(result), seo.META_DESCRIPTION_MAX_LENGTH)
		self.assertTrue(result.endswith("…"))
		body = result[:-1]
		# clamp landed on a whole-word boundary (no trailing space, no partial word)
		self.assertFalse(body.endswith(" "))
		self.assertTrue(clean.startswith(body))
		self.assertNotIn("wor…", result)


class TestLangSwap(UnitTestCase):
	def test_swaps_en_to_ar(self):
		self.assertEqual(seo.swap_lang_in_path("/en/products/shoe", "ar"), "/ar/products/shoe")

	def test_swaps_ar_to_en(self):
		self.assertEqual(seo.swap_lang_in_path("/ar/products/shoe", "en"), "/en/products/shoe")

	def test_no_prefix_path_gets_lang_prepended(self):
		self.assertEqual(seo.swap_lang_in_path("/foo", "en"), "/en/foo")
		self.assertEqual(seo.swap_lang_in_path("/foo/bar", "ar"), "/ar/foo/bar")

	def test_empty_path_fallback(self):
		self.assertEqual(seo.swap_lang_in_path("", "en"), "/en/")
		self.assertEqual(seo.swap_lang_in_path(None, "ar"), "/ar/")


class TestBuildAlternates(IntegrationTestCase):
	def test_build_alternates_has_both_languages(self):
		alternates = seo.build_alternates("/en/products/shoe")
		self.assertEqual({alt["lang"] for alt in alternates}, {"en", "ar"})
		by_lang = {alt["lang"]: alt["href"] for alt in alternates}
		self.assertIn("/en/products/shoe", by_lang["en"])
		self.assertIn("/ar/products/shoe", by_lang["ar"])


class TestBuildPageSeo(IntegrationTestCase):
	def setUp(self):
		set_seo_settings(
			store_name="MyStore",
			seo_title_template="{title} | {store}",
			default_meta_description="Default store description.",
			default_share_image="/assets/share.png",
		)

	def test_full_key_set(self):
		result = seo.build_page_seo({})
		self.assertEqual(set(result.keys()), PAGE_SEO_KEYS)

	def test_overrides_win(self):
		source = {
			"meta_title": "Custom Title",
			"meta_description": "<b>Custom</b>   desc",
			"og_image": "/custom/over.png",
			"noindex": 1,
		}
		result = seo.build_page_seo(source, display_name="Ignored")
		self.assertEqual(result["title"], "Custom Title")
		self.assertEqual(result["description"], "Custom desc")
		self.assertIn("/custom/over.png", result["image"])
		self.assertIs(result["noindex"], True)

	def test_fallbacks_to_defaults(self):
		result = seo.build_page_seo({}, display_name="Home")
		self.assertEqual(result["title"], "Home | MyStore")
		self.assertEqual(result["description"], "Default store description.")
		self.assertIn("/assets/share.png", result["image"])
		self.assertIs(result["noindex"], False)
		self.assertEqual(result["type"], "website")

	def test_noindex_carried_as_bool(self):
		self.assertIs(seo.build_page_seo({"noindex": 1}).get("noindex"), True)
		self.assertIs(seo.build_page_seo({"noindex": 0}).get("noindex"), False)
		self.assertIs(seo.build_page_seo({}).get("noindex"), False)

	def test_page_type_passthrough(self):
		self.assertEqual(seo.build_page_seo({}, page_type="article")["type"], "article")


class TestBuildCollectionSeo(IntegrationTestCase):
	"""A category page keeps its per-category SEO overrides regardless of the product_list_* globals."""

	def set_product_list_seo(self, **values):
		"""Write the product-list SEO fields and bust the cached doc build_collection_seo reads through."""
		frappe.db.set_single_value("Commera Settings", "store_name", values.get("store_name", "MyStore"))
		for field in ("product_list_meta_title", "product_list_meta_description", "product_list_og_image"):
			frappe.db.set_single_value("Commera Settings", field, values.get(field, ""))
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

	def test_no_category_uses_configured_product_list_fields(self):
		self.set_product_list_seo(
			product_list_meta_title="All Products — Shop Everything",
			product_list_meta_description="<b>Browse</b> the full catalogue today.",
			product_list_og_image="/files/all-products.png",
		)
		result = seo.build_collection_seo(category=None, breadcrumbs=[])
		self.assertEqual(result["title"], "All Products — Shop Everything")
		self.assertEqual(result["description"], "Browse the full catalogue today.")
		self.assertIn("/files/all-products.png", result["image"])

	def test_no_category_falls_back_to_computed_default(self):
		self.set_product_list_seo(store_name="MyStore")
		result = seo.build_collection_seo(category=None, breadcrumbs=[])
		self.assertEqual(result["title"], "Products | MyStore")
		self.assertIn("Shop the latest products at MyStore", result["description"])
		# blank og_image falls through to the bundled default card
		self.assertIn(seo.DEFAULT_OG_IMAGE, result["image"])

	def test_category_ignores_product_list_globals(self):
		# A category page keeps its per-category override, never the all-products globals.
		self.set_product_list_seo(
			store_name="MyStore",
			product_list_meta_title="All Products — Shop Everything",
			product_list_meta_description="Browse the full catalogue today.",
		)
		category_doc = {"meta_title": "Shoes Collection", "meta_description": "All our shoes."}
		result = seo.build_collection_seo(
			category="Shoes", breadcrumbs=[], total_count=12, category_doc=category_doc
		)
		self.assertEqual(result["title"], "Shoes Collection")
		self.assertEqual(result["description"], "All our shoes.")

	def test_category_without_override_uses_category_default(self):
		self.set_product_list_seo(
			store_name="MyStore",
			product_list_meta_title="All Products — Shop Everything",
		)
		result = seo.build_collection_seo(category="Shoes", breadcrumbs=[], total_count=7)
		self.assertEqual(result["title"], "Shoes | MyStore")
		self.assertIn("Shop Shoes at MyStore", result["description"])


class TestBreadcrumbJsonLd(IntegrationTestCase):
	def test_leaf_crumb_omits_item(self):
		breadcrumbs = [
			{"label": "Home", "href": "/en"},
			{"label": "Shop", "href": "/en/products"},
			{"label": "Current Item", "href": "#"},
		]
		result = seo.build_breadcrumb_json_ld(breadcrumbs)
		items = result["itemListElement"]
		self.assertEqual(len(items), 3)
		self.assertEqual([item["position"] for item in items], [1, 2, 3])
		self.assertIn("item", items[0])
		self.assertIn("/en/products", items[1]["item"])
		# the "#" leaf is the current page; it must not carry a dead "item" link
		self.assertNotIn("item", items[2])

	def test_empty_href_omits_item(self):
		result = seo.build_breadcrumb_json_ld([{"label": "Leaf", "href": ""}])
		self.assertNotIn("item", result["itemListElement"][0])

	def test_skips_crumbs_without_label(self):
		breadcrumbs = [{"label": "Keep", "href": "/x"}, {"href": "/y"}, {"label": ""}]
		items = seo.build_breadcrumb_json_ld(breadcrumbs)["itemListElement"]
		self.assertEqual(len(items), 1)
		self.assertEqual(items[0]["name"], "Keep")
		self.assertEqual(items[0]["position"], 1)


class TestUtilityPageNoindexInjection(IntegrationTestCase):
	"""The theme renderer bypasses the www get_context controllers, so noindex comes via update_website_context."""

	def setUp(self):
		set_seo_settings(store_name="MyStore", seo_title_template="{title} | {store}")
		self.saved_request = getattr(frappe.local, "request", None)

	def tearDown(self):
		frappe.local.request = self.saved_request

	def run_context(self, path):
		frappe.local.request = frappe._dict(path=path)
		context = frappe._dict()
		website_context.update_website_context(context)
		return context

	def test_utility_paths_stay_noindex_without_json_ld(self):
		for path in ("/en/cart", "/ar/account/dashboard", "/en/login"):
			context = self.run_context(path)
			self.assertIs(context.seo["noindex"], True)
			# noindex pages carry no structured data
			self.assertEqual(context.json_ld, [])

	def test_utility_page_title_names_the_page(self):
		self.assertEqual(self.run_context("/en/cart").seo["title"], "Cart | MyStore")
		self.assertEqual(self.run_context("/ar/account/dashboard").seo["title"], "My Account | MyStore")
		self.assertEqual(self.run_context("/en/login").seo["title"], "Login | MyStore")

	def test_utility_paths_bypass_the_page_cache(self):
		# Per-user cart/account markup must never be cached and served to another shopper.
		self.assertEqual(self.run_context("/en/cart").no_cache, 1)

	def test_unrelated_path_gets_no_seo_override(self):
		# Theme content pages (home/products) own their own seo block; we must not inject here.
		context = self.run_context("/en/products")
		self.assertNotIn("seo", context)
		self.assertNotIn("json_ld", context)

	def test_unprefixed_utility_path_is_not_matched(self):
		# The pattern is language-anchored; a bare /cart is not a storefront route.
		self.assertNotIn("seo", self.run_context("/cart"))


class SitemapFixtureMixin:
	"""Seeds one published / one noindex / one unpublished variant and two categories (enabled + noindex)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.suffix = frappe.generate_hash(length=8)
		cls.configurator = get_test_configurator()
		cls.item = get_test_item()

		cls.published_route = f"seo-test-pub-{cls.suffix}"
		cls.noindex_route = f"seo-test-noindex-{cls.suffix}"
		cls.unpublished_route = f"seo-test-unpub-{cls.suffix}"
		cls.category_slug = f"seotestcat{cls.suffix}"
		cls.noindex_category_slug = f"seotestcatni{cls.suffix}"

		cls.make_variant(cls.published_route, is_published=1, noindex=0)
		cls.make_variant(cls.noindex_route, is_published=1, noindex=1)
		cls.make_variant(cls.unpublished_route, is_published=0, noindex=0)

		cls.make_category(cls.category_slug, enabled=1, noindex=0)
		cls.make_category(cls.noindex_category_slug, enabled=1, noindex=1)

	@classmethod
	def make_variant(cls, route, is_published, noindex):
		variant = frappe.new_doc("Style Attribute Variant")
		variant.configurator = cls.configurator
		variant.item_style = cls.item
		variant.attribute_value = f"Val {frappe.generate_hash(length=6)}"
		variant.display_name = f"Display {route}"
		variant.route = route
		variant.noindex = noindex
		# images + sizes are required or validate() force-unpublishes the variant
		variant.append("images", {"image": "/assets/seo-test.jpg"})
		variant.append("sizes", {"size": "M", "item_code": cls.item})
		variant.is_published = is_published
		variant.insert(ignore_permissions=True)
		return variant

	@classmethod
	def make_category(cls, route_slug, enabled, noindex):
		category = frappe.new_doc("Ecommerce Category")
		category.category_name = f"SEO Cat {route_slug}"
		category.display_name = category.category_name
		category.route_slug = route_slug
		category.enabled = enabled
		category.noindex = noindex
		category.insert(ignore_permissions=True)
		return category

	def url(self, path):
		from frappe.utils import get_url

		return get_url(path)


class TestSitemapIndex(SitemapFixtureMixin, IntegrationTestCase):
	def get_index(self):
		context = frappe._dict()
		sitemap.get_context(context)
		return context

	def child_pages(self, context, seg_type):
		token = f"/sitemap-{seg_type}-"
		return [entry for entry in context.sitemaps if token in entry["loc"]]

	def test_index_lists_only_child_sitemaps(self):
		# The index is a <sitemapindex>; it must never emit <url> entries itself.
		context = self.get_index()
		self.assertTrue(context.sitemaps)
		self.assertTrue(all("loc" in entry and "lastmod" in entry for entry in context.sitemaps))

	def test_product_child_count_matches_pagination_math(self):
		context = self.get_index()
		total = frappe.db.count("Style Attribute Variant", {"is_published": 1, "noindex": 0})
		expected = -(-total // sitemap_segment.get_docs_per_page())
		self.assertEqual(len(self.child_pages(context, "products")), expected)

	def test_pages_segment_has_exactly_one_child(self):
		# The homepage-only segment never paginates, so it always contributes one child.
		context = self.get_index()
		self.assertEqual(len(self.child_pages(context, "pages")), 1)

	def test_child_locs_are_one_based(self):
		context = self.get_index()
		product_locs = [entry["loc"] for entry in self.child_pages(context, "products")]
		self.assertTrue(any(loc.endswith("/sitemap-products-1.xml") for loc in product_locs))
		self.assertFalse(any(loc.endswith("/sitemap-products-0.xml") for loc in product_locs))

	def test_no_cache_flag_set(self):
		context = self.get_index()
		self.assertEqual(context.no_cache, 1)


class TestSitemapSegment(SitemapFixtureMixin, IntegrationTestCase):
	def run_segment(self, seg_type, page):
		context = frappe._dict()
		frappe.local.form_dict = frappe._dict(seg_type=seg_type, page=str(page))
		sitemap_segment.get_context(context)
		return context

	def locs(self, seg_type, page):
		return {entry["loc"] for entry in self.run_segment(seg_type, page).urls}

	def test_published_variant_present_in_both_languages(self):
		# Freshly inserted rows sort newest-first, so the fixtures land on page 1.
		locs = self.locs("products", 1)
		self.assertIn(self.url(f"/en/products/{self.published_route}"), locs)
		self.assertIn(self.url(f"/ar/products/{self.published_route}"), locs)

	def test_noindex_variant_excluded(self):
		locs = self.locs("products", 1)
		self.assertNotIn(self.url(f"/en/products/{self.noindex_route}"), locs)
		self.assertNotIn(self.url(f"/ar/products/{self.noindex_route}"), locs)

	def test_unpublished_variant_excluded(self):
		locs = self.locs("products", 1)
		self.assertNotIn(self.url(f"/en/products/{self.unpublished_route}"), locs)
		self.assertNotIn(self.url(f"/ar/products/{self.unpublished_route}"), locs)

	def test_enabled_category_present_noindex_excluded(self):
		locs = self.locs("collections", 1)
		self.assertIn(self.url(f"/en/products?category={self.category_slug}"), locs)
		self.assertIn(self.url(f"/ar/products?category={self.category_slug}"), locs)
		self.assertNotIn(self.url(f"/en/products?category={self.noindex_category_slug}"), locs)

	def test_homepage_rides_first_pages_child(self):
		locs = self.locs("pages", 1)
		self.assertIn(self.url("/en"), locs)
		self.assertIn(self.url("/ar"), locs)

	def test_pages_segment_is_homepage_only(self):
		# commera has no CMS page doctype, so this segment carries exactly the two homepage URLs.
		self.assertEqual(
			self.locs("pages", 1),
			{self.url("/en"), self.url("/ar")},
		)

	def test_pages_segment_has_a_single_child(self):
		self.assertEqual(sitemap_segment.segment_page_count("pages"), 1)

	def test_pages_segment_second_child_is_empty(self):
		# The homepage must not be duplicated onto a phantom second child sitemap.
		self.assertEqual(self.run_segment("pages", 2).urls, [])

	def test_pages_segment_has_no_lastmod_source(self):
		self.assertIsNone(sitemap_segment.latest_lastmod("pages"))

	def test_page_never_exceeds_url_cap(self):
		# One product route per language; a full page must stay within the sitemaps.org 50k-URL ceiling.
		context = self.run_segment("products", 1)
		self.assertLessEqual(len(context.urls), sitemap_segment.DEFAULT_URLS_PER_SITEMAP)

	def test_consecutive_pages_are_disjoint_slices(self):
		# Only meaningful when the catalogue spills past one page; skip otherwise.
		total = frappe.db.count("Style Attribute Variant", {"is_published": 1, "noindex": 0})
		if total <= sitemap_segment.get_docs_per_page():
			self.skipTest("catalogue fits in a single product child sitemap")
		page_one = self.locs("products", 1)
		page_two = self.locs("products", 2)
		self.assertEqual(len(page_one), sitemap_segment.DEFAULT_URLS_PER_SITEMAP)
		self.assertTrue(page_one.isdisjoint(page_two))

	def test_out_of_range_page_renders_empty(self):
		total = frappe.db.count("Style Attribute Variant", {"is_published": 1, "noindex": 0})
		beyond = (total // sitemap_segment.get_docs_per_page()) + 5
		context = self.run_segment("products", beyond)
		self.assertEqual(context.urls, [])

	def test_invalid_page_renders_empty(self):
		self.assertEqual(self.run_segment("products", 0).urls, [])

	def test_unknown_segment_renders_empty(self):
		self.assertEqual(self.run_segment("widgets", 1).urls, [])

	def test_docs_per_page_honours_settings(self):
		# The per-page budget is set in Commera Settings and split across the storefront languages.
		original = frappe.db.get_single_value("Commera Settings", "sitemap_urls_per_page")
		try:
			frappe.db.set_single_value("Commera Settings", "sitemap_urls_per_page", 10)
			self.assertEqual(
				sitemap_segment.get_docs_per_page(),
				10 // len(sitemap_segment.LANGUAGES),
			)
		finally:
			frappe.db.set_single_value("Commera Settings", "sitemap_urls_per_page", original)

	def test_no_cache_flag_set(self):
		self.assertEqual(self.run_segment("products", 1).no_cache, 1)


class TestBuildProductJsonLd(IntegrationTestCase):
	def base_variant(self, **overrides):
		variant = {"display_name": "Running Shoe", "item_style": "STYLE-1"}
		variant.update(overrides)
		return variant

	def test_stored_override_wins_over_generated_shape(self):
		override = {"@context": "https://schema.org", "@type": "Product", "name": "Hand Written"}
		result = seo.build_product_json_ld(
			self.base_variant(json_ld=frappe.as_json(override)),
			{"item_code": "SKU-1", "item_name": "Ignored"},
			images=["/files/a.png"],
			price=99,
		)
		self.assertEqual(result, override)

	def test_unparseable_override_falls_back_to_generated(self):
		# A half-edited override must not take down the page's structured data.
		result = seo.build_product_json_ld(
			self.base_variant(json_ld="{not json"),
			{"item_code": "SKU-1"},
			images=[],
		)
		self.assertEqual(result["@type"], "Product")
		self.assertEqual(result["name"], "Running Shoe")

	def test_offer_carries_price_currency_and_availability(self):
		result = seo.build_product_json_ld(
			self.base_variant(),
			{"item_code": "SKU-1", "brand": "Acme"},
			images=["/files/a.png"],
			price=1234.5,
			availability="InStock",
			currency="AED",
		)
		self.assertEqual(result["offers"]["price"], "1234.50")
		self.assertEqual(result["offers"]["priceCurrency"], "AED")
		self.assertEqual(result["offers"]["availability"], "https://schema.org/InStock")
		self.assertEqual(result["brand"], {"@type": "Brand", "name": "Acme"})
		self.assertEqual(result["sku"], "SKU-1")

	def test_out_of_stock_maps_to_schema_url(self):
		result = seo.build_product_json_ld(
			self.base_variant(), {"item_code": "SKU-1"}, images=[], price=10, availability="OutOfStock"
		)
		self.assertEqual(result["offers"]["availability"], "https://schema.org/OutOfStock")

	def test_unknown_availability_omits_the_key(self):
		result = seo.build_product_json_ld(
			self.base_variant(), {"item_code": "SKU-1"}, images=[], price=10, availability="Backordered"
		)
		self.assertNotIn("availability", result["offers"])

	def test_priceless_product_has_no_offer_block(self):
		result = seo.build_product_json_ld(self.base_variant(), {"item_code": "SKU-1"}, images=[])
		self.assertNotIn("offers", result)

	def test_images_are_absolutised_and_blanks_dropped(self):
		result = seo.build_product_json_ld(
			self.base_variant(), {"item_code": "SKU-1"}, images=["/files/a.png", "", None]
		)
		self.assertEqual(len(result["image"]), 1)
		self.assertTrue(result["image"][0].startswith("http"))
		self.assertTrue(result["image"][0].endswith("/files/a.png"))

	def test_sku_falls_back_to_item_style(self):
		result = seo.build_product_json_ld(self.base_variant(), {}, images=[])
		self.assertEqual(result["sku"], "STYLE-1")
		self.assertEqual(result["mpn"], "STYLE-1")


class TestGenerateProductJsonLd(SitemapFixtureMixin, IntegrationTestCase):
	"""The Desk preview button routes through get_product_detail, so price and stock match the product page."""

	def test_generated_schema_matches_product_detail(self):
		from commera.product_detail import get_product_detail

		variant_name = frappe.db.get_value("Style Attribute Variant", {"route": self.published_route}, "name")
		schema = frappe.parse_json(seo.generate_product_json_ld(variant_name))
		detail = get_product_detail(self.published_route)

		self.assertEqual(schema["@type"], "Product")
		self.assertEqual(schema["name"], f"Display {self.published_route}")
		expected_price = detail["sale_price"] or detail["default_price"]
		if expected_price:
			self.assertEqual(schema["offers"]["price"], f"{expected_price:.2f}")
		else:
			self.assertNotIn("offers", schema)

	def test_stored_override_is_ignored_by_the_preview(self):
		# The button previews the *generated* shape so an admin can diff it against a stale override.
		variant_name = frappe.db.get_value("Style Attribute Variant", {"route": self.published_route}, "name")
		frappe.db.set_value(
			"Style Attribute Variant", variant_name, "json_ld", '{"@type": "Stale"}', update_modified=False
		)
		frappe.clear_document_cache("Style Attribute Variant", variant_name)
		schema = frappe.parse_json(seo.generate_product_json_ld(variant_name))
		self.assertEqual(schema["@type"], "Product")

	def test_unpublished_variant_throws(self):
		variant_name = frappe.db.get_value(
			"Style Attribute Variant", {"route": self.unpublished_route}, "name"
		)
		with self.assertRaises(frappe.ValidationError):
			seo.generate_product_json_ld(variant_name)
