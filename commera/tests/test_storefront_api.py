import frappe

from commera.api.storefront.collections import get_collection, get_collections
from commera.api.storefront.products import get_product, get_products
from commera.api.storefront.shop import get_page, get_sitemap, get_storefront_url
from commera.sdk import catalog, shop
from commera.sdk.catalog import get_collection_handle
from commera.sdk.shop import get_menu_link
from commera.sdk.types import Collection, Product, ProductCard, ProductPage, ProductVariant, Shop
from commera.tests.test_product_details import ProductDetailPriceTestCase


class TestStorefrontApi(ProductDetailPriceTestCase):
	def assert_shape(self, result: dict, shape):
		self.assertEqual(set(result), shape.__required_keys__ | shape.__optional_keys__)

	def test_shopper_reads_have_exactly_their_declared_keys(self):
		route = self.make_priced_variant("SHAPE", default_rate=40, sale_rate=30)
		page = catalog.list_products(collection=get_collection_handle(self.item_group))
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
		self.assertEqual(product["collection"]["handle"], get_collection_handle(self.item_group))

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

	def test_a_collection_lists_only_its_own_products(self):
		route = self.make_priced_variant("LISTED", default_rate=30, sale_rate=20)

		result = get_products(collection=get_collection_handle(self.item_group))

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
		collection = get_collection_handle(self.item_group)

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

	def test_a_collection_needs_a_published_product(self):
		handle = get_collection_handle(self.item_group)
		with self.assertRaises(frappe.DoesNotExistError):
			get_collection(handle)

		self.make_priced_variant("SHOWN", default_rate=10)

		self.assertEqual(get_collection(handle)["title"], self.item_group)
		self.assertIn(handle, [collection["handle"] for collection in get_collections()])

	def test_the_sitemap_leaves_out_noindex_products(self):
		shown = self.make_priced_variant("INDEXED", default_rate=10)
		hidden = self.make_priced_variant("NOINDEX", default_rate=10)
		frappe.db.set_value("Style Attribute Variant", {"route": hidden}, "noindex", 1)

		handles = [row["handle"] for row in get_sitemap()["products"]]

		self.assertIn(shown, handles)
		self.assertNotIn(hidden, handles)

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
		handle = get_collection_handle(self.item_group)

		self.assertEqual(get_menu_link(node), ("collection", handle))
		self.assertEqual(
			get_menu_link({"link_type": "Brand", "brand": "K&N", "parent": ""}), ("brand", "K&N")
		)
		self.assertEqual(
			get_menu_link({"link_type": "Item Group", "item_groups": [], "parent": ""}), ("all", None)
		)
		self.assertEqual(
			get_storefront_url({"type": "collection", "target": handle}), f"/collections/{handle}"
		)
		self.assertEqual(get_storefront_url({"type": "brand", "target": "K&N"}), "/search?q=K%26N")
		self.assertEqual(get_storefront_url({"type": "all", "target": None}), "/collections/all")
