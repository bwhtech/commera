from unittest.mock import patch

import frappe

from commera.api.storefront.collections import get_collection, get_collections
from commera.api.storefront.products import get_product, get_products
from commera.api.storefront.shop import get_page, get_sitemap, get_storefront_url
from commera.sdk import catalog, shop
from commera.sdk.shop import get_menu_link
from commera.sdk.types import Collection, Product, ProductCard, ProductPage, ProductVariant, Shop
from commera.tests.test_product_details import ProductDetailPriceTestCase
from commera.www.sitemap_segment import get_urls_per_page


class TestStorefrontApi(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		self.collection = self.make_collection()

	def make_collection(self, link_item_group=True) -> str:
		category = frappe.new_doc("Ecommerce Category")
		category.category_name = f"Details Tab {frappe.generate_hash(length=8)}"
		category.enabled = 1
		if link_item_group:
			category.link_type = "Item Group"
			category.append("link_item_groups", {"item_group": self.item_group})
		category.insert(ignore_permissions=True)
		frappe.local.commera_storefront_menu = None
		self.addCleanup(setattr, frappe.local, "commera_storefront_menu", None)
		return category.route_slug

	def assert_shape(self, result: dict, shape):
		self.assertEqual(set(result), shape.__required_keys__ | shape.__optional_keys__)

	def test_shopper_reads_have_exactly_their_declared_keys(self):
		route = self.make_priced_variant("SHAPE", default_rate=40, sale_rate=30)
		page = catalog.list_products(collection=self.collection)
		product = catalog.get_product(route)

		self.assert_shape(page, ProductPage)
		self.assert_shape(page["products"][0], ProductCard)
		self.assert_shape(product, Product)
		self.assert_shape(product["variants"][0], ProductVariant)
		self.assert_shape(catalog.list_collections()[0], Collection)
		self.assert_shape(shop.get_shop(), Shop)

	def test_a_product_lists_its_sizes_as_variants_with_sale_and_list_prices(self):
		route = self.make_priced_variant("API", default_rate=100, sale_rate=80)

		product = get_product(route)

		self.assertEqual(product["handle"], route)
		self.assertEqual(product["price"], 80)
		self.assertEqual(
			[
				(variant["title"], variant["price"], variant["compare_at_price"])
				for variant in product["variants"]
			],
			[("M", 80, 100)],
		)
		self.assertEqual(product["collection"]["handle"], self.collection)

	def test_a_variant_without_stock_is_not_available(self):
		route = self.make_priced_variant("NOSTOCK", default_rate=50)

		product = get_product(route)

		self.assertFalse(product["variants"][0]["available"])
		self.assertFalse(product["available"])

	def test_an_unpublished_product_is_not_found(self):
		route = self.make_priced_variant("HIDDEN", default_rate=50)
		frappe.db.set_value("Style Attribute Variant", {"route": route}, "is_published", 0)

		with self.assertRaises(frappe.DoesNotExistError):
			get_product(route)

	def test_an_unknown_product_is_not_found_without_naming_the_doctype(self):
		frappe.local.message_log = []

		with self.assertRaisesRegex(frappe.DoesNotExistError, "^Product no-such-product not found$"):
			get_product("no-such-product")

		self.assertEqual(frappe.local.message_log, [])

	def test_facets_are_cached_for_each_filter_set(self):
		with patch("commera.sdk.catalog.get_listing_facet_counts", return_value={}) as count_facets:
			get_products(collection=self.collection, brands="No Brand")
			get_products(collection=self.collection, brands="No Brand", page=2)
			get_products(collection=self.collection, brands="Other Brand")

		self.assertEqual(count_facets.call_count, 2)

	def test_a_collection_lists_only_its_own_products(self):
		route = self.make_priced_variant("LISTED", default_rate=30, sale_rate=20)

		result = get_products(collection=self.collection)

		self.assertEqual([card["handle"] for card in result["products"]], [route])
		self.assertEqual(result["total"], 1)
		self.assertEqual(
			(result["products"][0]["price"], result["products"][0]["compare_at_price"]), (20, 30)
		)

	def test_facets_count_the_products_of_each_value(self):
		brands = [f"Brand A {self.suffix}", f"Brand B {self.suffix}"]
		colors = []
		for label, brand in zip(("FACETA", "FACETB"), brands, strict=True):
			route = self.make_priced_variant(label, default_rate=10)
			variant, color = frappe.db.get_value(
				"Style Attribute Variant", {"route": route}, ["name", "attribute_value"]
			)
			# make_variant gives every product the configurator's item style, so each gets its own here.
			item_code = frappe.db.get_value("Color Size Item", {"parent": variant}, "item_code")
			frappe.db.set_value("Style Attribute Variant", variant, "item_style", item_code)
			frappe.db.set_value("Item", item_code, "brand", brand)
			colors.append(color)
		collection = self.collection

		facets = get_products(collection=collection)["facets"]

		self.assertEqual(facets["brands"], [{"value": brand, "count": 1} for brand in brands])
		self.assertEqual(
			sorted(facets["colors"], key=lambda color: color["value"]),
			[{"value": color, "count": 1} for color in sorted(colors)],
		)
		self.assertEqual(facets["sizes"], [{"value": "M", "count": 2}])

		# A brand narrows the other facets but not its own, so the shopper can still widen the selection.
		narrowed = get_products(collection=collection, brands=brands[0])["facets"]

		self.assertEqual([brand["value"] for brand in narrowed["brands"]], brands)
		self.assertEqual(narrowed["colors"], [{"value": colors[0], "count": 1}])
		self.assertEqual(narrowed["sizes"], [{"value": "M", "count": 1}])

	def test_an_unknown_sort_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Sort must be one of"):
			get_products(sort="random")

	def test_a_collection_is_an_enabled_menu_tab(self):
		self.assertEqual(
			get_collection(self.collection)["title"],
			frappe.db.get_value("Ecommerce Category", {"route_slug": self.collection}, "display_name"),
		)
		self.assertIn(self.collection, [collection["handle"] for collection in get_collections()])

		frappe.db.set_value("Ecommerce Category", {"route_slug": self.collection}, "enabled", 0)
		frappe.local.commera_storefront_menu = None
		with self.assertRaises(frappe.DoesNotExistError):
			get_collection(self.collection)
		with self.assertRaises(frappe.DoesNotExistError):
			get_products(collection=self.collection)

	def test_a_tab_without_item_groups_lists_every_product_like_its_listing_page(self):
		self.make_priced_variant("ALLTAB", default_rate=10)
		every_product = self.make_collection(link_item_group=False)

		self.assertEqual(get_products(collection=every_product)["total"], get_products()["total"])

	def test_the_sitemap_leaves_out_noindex_products(self):
		shown = self.make_priced_variant("INDEXED", default_rate=10)
		hidden = self.make_priced_variant("NOINDEX", default_rate=10)
		frappe.db.set_value("Style Attribute Variant", {"route": hidden}, "noindex", 1)

		handles = [row["handle"] for row in get_sitemap()["products"]]

		self.assertIn(shown, handles)
		self.assertNotIn(hidden, handles)

	def test_the_sitemap_pages_each_kind_and_counts_its_handles(self):
		self.make_priced_variant("PAGEA", default_rate=10)
		self.make_priced_variant("PAGEB", default_rate=10)
		total = frappe.db.count("Style Attribute Variant", {"is_published": 1, "noindex": 0})

		first = get_sitemap()
		with patch("commera.sdk.shop.get_urls_per_page", return_value=1):
			second_page = get_sitemap(kind="products", page=2)

		self.assertEqual(set(first), {"products", "collections", "pages", "total", "page", "page_size"})
		self.assertEqual((first["page"], first["page_size"]), (1, get_urls_per_page()))
		self.assertEqual(first["total"]["products"], total)
		self.assertEqual(first["total"]["collections"], len(first["collections"]))
		self.assertEqual(set(second_page), {"products", "total", "page", "page_size"})
		self.assertEqual(second_page["total"], {"products": total})
		self.assertEqual(second_page["products"], first["products"][1:2])

	def test_the_sitemap_lists_published_pages_and_collections_by_handle(self):
		page = frappe.get_doc(
			{
				"doctype": "Shop Web Page",
				"route": f"about-{self.suffix.lower()}",
				"content": "About",
				"published": 1,
			}
		).insert(ignore_permissions=True, set_name=f"About {self.suffix}")

		sitemap = get_sitemap()

		self.assertIn(page.route, [row["handle"] for row in sitemap["pages"]])
		self.assertIn(self.collection, [row["handle"] for row in sitemap["collections"]])

	def test_an_unknown_sitemap_kind_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Sitemap kind must be one of"):
			get_sitemap(kind="brands")

	def test_a_draft_page_is_not_found(self):
		page = frappe.get_doc(
			{
				"doctype": "Shop Web Page",
				"route": f"draft-{self.suffix.lower()}",
				"content": "Draft",
				"published": 0,
			}
		).insert(ignore_permissions=True, set_name=f"Draft {self.suffix}")

		with self.assertRaises(frappe.DoesNotExistError):
			get_page(page.route)

	def test_the_sdk_returns_none_where_the_api_answers_404(self):
		route = self.make_priced_variant("SDKHIDDEN", default_rate=50)
		frappe.db.set_value("Style Attribute Variant", {"route": route}, "is_published", 0)

		self.assertIsNone(catalog.get_product(route))
		self.assertIsNone(catalog.get_collection("no-such-collection"))

	def test_menu_links_name_their_target_and_the_api_adds_storefront_paths(self):
		node = {"link_type": "Item Group", "item_groups": [self.item_group], "parent": "Root"}
		handle = self.collection

		self.assertEqual(get_menu_link(node, handle), ("collection", handle))
		self.assertEqual(
			get_menu_link({"link_type": "Brand", "brand": "K&N", "parent": ""}, handle), ("brand", "K&N")
		)
		self.assertEqual(
			get_menu_link({"link_type": "", "item_groups": [], "parent": ""}, handle), ("collection", handle)
		)
		self.assertEqual(
			get_menu_link({"link_type": "", "item_groups": [], "parent": "Root"}, handle), (None, None)
		)
		self.assertEqual(
			get_storefront_url({"type": "collection", "target": handle}), f"/collections/{handle}"
		)
		self.assertEqual(get_storefront_url({"type": "brand", "target": "K&N"}), "/search?q=K%26N")
		self.assertEqual(get_storefront_url({"type": "all", "target": None}), "/collections/all")
