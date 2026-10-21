import frappe

from commera.api.storefront.collections import get_collection, get_collection_handle, get_collections
from commera.api.storefront.products import get_product, get_products
from commera.api.storefront.shop import get_menu_url, get_page, get_sitemap
from commera.tests.test_product_details import ProductDetailPriceTestCase


class TestStorefrontApi(ProductDetailPriceTestCase):
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

	def test_menu_links_open_collections_and_brand_searches(self):
		node = {"link_type": "Item Group", "item_groups": [self.item_group], "parent": "Root"}

		self.assertEqual(get_menu_url(node), f"/collections/{get_collection_handle(self.item_group)}")
		self.assertEqual(
			get_menu_url({"link_type": "Brand", "brand": "K&N", "parent": ""}), "/search?q=K%26N"
		)
		self.assertEqual(
			get_menu_url({"link_type": "Item Group", "item_groups": [], "parent": ""}), "/collections/all"
		)
