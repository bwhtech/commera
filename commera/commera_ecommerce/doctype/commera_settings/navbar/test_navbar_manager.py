# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

import copy
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.nestedset import get_root_of, rebuild_tree

from commera.commera_ecommerce.doctype.bulk_publish_variants import bulk_publish_variants
from commera.commera_ecommerce.doctype.commera_settings.navbar import navbar_manager
from commera.commera_ecommerce.doctype.ecommerce_category.ecommerce_category import (
	get_menu_tree,
)
from commera.search import sync
from commera.search.engine_cache import clear_search_engine
from commera.search.sqlite_product_search import SqliteProductSearch
from commera.tests import delete_menu_entries

ITEM_GROUP_SNAPSHOT_FIELDS = ["name", "parent_item_group", "is_group", "lft", "rgt", "modified"]


def make_item_group(name, parent=None):
	return frappe.get_doc(
		{
			"doctype": "Item Group",
			"item_group_name": name,
			# commera makes the storefront display name mandatory on Item Group.
			"custom_displayname": name,
			"parent_item_group": parent or get_root_of("Item Group"),
			"is_group": 1,
		}
	).insert()


def find_node(menu, name):
	for node in menu:
		if node["name"] == name:
			return node
		found = find_node(node["children"], name)
		if found:
			return found
	return None


class TestNavbarManager(IntegrationTestCase):
	def setUp(self):
		make_item_group("Test MM Shirts")
		make_item_group("Test MM Bags")
		make_item_group("Test MM Belts")
		frappe.get_doc({"doctype": "Brand", "brand": "Test MM Brand 1"}).insert()

		self.men = self.add_node(None, "Test MM Men")["name"]
		self.women = self.add_node(None, "Test MM Women")["name"]

	def tearDown(self):
		# IntegrationTestCase rolls back once per class, so each test must clear its own rows.
		delete_menu_entries({"name": ["like", "Test MM%"]})
		frappe.db.delete("Item Group", {"name": ["like", "Test MM%"]})
		frappe.db.delete("Brand", {"name": ["like", "Test MM%"]})

	def item_group_snapshot(self):
		return frappe.get_all(
			"Item Group", fields=ITEM_GROUP_SNAPSHOT_FIELDS, order_by="name asc", limit_page_length=0
		)

	def add_node(self, parent, display_name, link_type=None, link_target=None):
		menu = navbar_manager.add_node(
			parent=parent, display_name=display_name, link_type=link_type, link_target=link_target
		)["menu"]
		return find_node(menu, self.last_added(parent, display_name))

	def last_added(self, parent, display_name):
		return frappe.get_all(
			"Ecommerce Category",
			filters={"parent_ecommerce_category": parent or "", "display_name": display_name},
			order_by="creation desc",
			limit=1,
			pluck="name",
		)[0]

	def test_editing_the_menu_never_touches_item_group(self):
		accessories = self.add_node(self.men, "Test MM Accessories")
		bags = self.add_node(accessories["name"], "Test MM Bags", "Item Group", ["Test MM Bags"])

		before = self.item_group_snapshot()

		navbar_manager.update_node(bags["name"], display_name="Test MM Handbags")
		navbar_manager.reorder_nodes("", [self.women, self.men])
		navbar_manager.move_node(accessories["name"], self.women, 0)
		navbar_manager.set_visibility(bags["name"], 0)
		navbar_manager.add_node(parent=self.men, display_name="Test MM Shoes")

		self.assertEqual(before, self.item_group_snapshot())

	def test_deleting_a_node_never_touches_item_group(self):
		shoes = self.add_node(self.men, "Test MM Shoes", "Item Group", ["Test MM Shirts"])
		before = self.item_group_snapshot()

		navbar_manager.delete_node(shoes["name"])

		self.assertFalse(frappe.db.exists("Ecommerce Category", shoes["name"]))
		self.assertEqual(before, self.item_group_snapshot())

	def test_add_node_derives_a_unique_key_from_the_parent_path(self):
		men_bags = self.add_node(self.men, "Test MM Bags")
		women_bags = self.add_node(self.women, "Test MM Bags")

		self.assertNotEqual(men_bags["name"], women_bags["name"])
		self.assertEqual(men_bags["label"], women_bags["label"])
		self.assertTrue(men_bags["name"].startswith(self.men))
		self.assertTrue(women_bags["name"].startswith(self.women))

	def test_repeated_labels_stay_independent_across_arms(self):
		men_bags = self.add_node(self.men, "Test MM Bags")
		women_bags = self.add_node(self.women, "Test MM Bags")

		navbar_manager.update_node(men_bags["name"], display_name="Test MM Man Bags")

		menu = navbar_manager.get_menu_editor_data()["menu"]
		self.assertEqual(find_node(menu, men_bags["name"])["label"], "Test MM Man Bags")
		self.assertEqual(find_node(menu, women_bags["name"])["label"], "Test MM Bags")

	def test_node_links_to_one_item_group(self):
		bags = self.add_node(self.men, "Test MM Bags", "Item Group", ["Test MM Bags"])

		self.assertEqual(bags["item_groups"], ["Test MM Bags"])
		self.assertIn("subcategory=Test%20MM%20Bags", bags["href"])

	def test_link_type_brand_and_url(self):
		brand = self.add_node(self.men, "Test MM Brand Tab", "Brand", "Test MM Brand 1")
		external = self.add_node(self.men, "Test MM Blog", "URL", "https://example.com/blog")
		heading = self.add_node(self.men, "Test MM Heading")

		self.assertIn("brands=Test%20MM%20Brand%201", brand["href"])
		self.assertEqual(external["href"], "https://example.com/blog")
		self.assertIsNone(heading["href"])

	def test_add_node_blocked_past_max_depth(self):
		column = self.add_node(self.men, "Test MM Accessories")
		self.add_node(column["name"], "Test MM Bags")

		bags = self.last_added(column["name"], "Test MM Bags")
		with self.assertRaises(frappe.ValidationError):
			navbar_manager.add_node(parent=bags, display_name="Test MM Too Deep")

	def test_move_node_blocked_when_its_subtree_would_exceed_depth(self):
		column = self.add_node(self.men, "Test MM Accessories")
		self.add_node(column["name"], "Test MM Bags")
		women_column = self.add_node(self.women, "Test MM Sale")

		with self.assertRaises(frappe.ValidationError):
			navbar_manager.move_node(column["name"], women_column["name"], 0)

	def test_move_node_reparents_and_renumbers_both_sides(self):
		first = self.add_node(self.men, "Test MM Accessories")
		second = self.add_node(self.men, "Test MM Shoes")
		self.add_node(self.women, "Test MM Sale")

		menu = navbar_manager.move_node(first["name"], self.women, 0)["menu"]

		self.assertEqual(
			frappe.db.get_value("Ecommerce Category", first["name"], "parent_ecommerce_category"),
			self.women,
		)
		self.assertEqual(frappe.db.get_value("Ecommerce Category", first["name"], "display_order"), 1)
		self.assertEqual(frappe.db.get_value("Ecommerce Category", second["name"], "display_order"), 1)
		self.assertEqual(
			[child["label"] for child in find_node(menu, self.men)["children"]], ["Test MM Shoes"]
		)

	def test_reorder_nodes_writes_display_order_only(self):
		menu = navbar_manager.reorder_nodes("", [self.women, self.men])["menu"]

		self.assertEqual(frappe.db.get_value("Ecommerce Category", self.women, "display_order"), 1)
		self.assertEqual(frappe.db.get_value("Ecommerce Category", self.men, "display_order"), 2)
		names = [node["name"] for node in menu]
		self.assertLess(names.index(self.women), names.index(self.men))

	def test_reorder_nodes_rejects_a_foreign_sibling(self):
		child = self.add_node(self.men, "Test MM Accessories")
		with self.assertRaises(frappe.ValidationError):
			navbar_manager.reorder_nodes("", [self.men, child["name"]])

	def test_delete_node_takes_its_whole_subtree(self):
		column = self.add_node(self.men, "Test MM Accessories")["name"]
		leaf = self.add_node(column, "Test MM Bags Tab", "Item Group", ["Test MM Bags"])["name"]

		menu = navbar_manager.delete_node(self.men)["menu"]

		for name in (self.men, column, leaf):
			self.assertFalse(frappe.db.exists("Ecommerce Category", name))
			self.assertIsNone(find_node(menu, name))
		self.assertTrue(frappe.db.exists("Ecommerce Category", self.women), "a sibling tab was deleted")

	def test_set_visibility_writes_enabled(self):
		navbar_manager.set_visibility(self.men, 0)
		self.assertEqual(frappe.db.get_value("Ecommerce Category", self.men, "enabled"), 0)

		navbar_manager.set_visibility(self.men, 1)
		self.assertEqual(frappe.db.get_value("Ecommerce Category", self.men, "enabled"), 1)

	def test_hiding_a_tab_hides_its_whole_branch(self):
		column = self.add_node(self.men, "Test MM Accessories")
		navbar_manager.set_visibility(self.men, 0)

		storefront_menu = get_menu_tree(enabled_only=True)
		self.assertIsNone(find_node(storefront_menu, self.men))
		self.assertIsNone(find_node(storefront_menu, column["name"]))

	def make_deep_item_group_tree(self):
		"""Four levels of catalog — one more than the menu can render."""
		make_item_group("Test MM Catalog")
		make_item_group("Test MM Level 2", "Test MM Catalog")
		make_item_group("Test MM Level 3", "Test MM Level 2")
		make_item_group("Test MM Level 4", "Test MM Level 3")

	def imported_names(self):
		return frappe.get_all(
			"Ecommerce Category", filters={"category_name": ["like", "Test MM Catalog%"]}, pluck="name"
		)

	def test_import_stops_at_the_depth_cap_and_never_touches_item_group(self):
		self.make_deep_item_group_tree()
		before = self.item_group_snapshot()

		menu = navbar_manager.import_from_item_group(item_group="Test MM Catalog")["menu"]

		catalog = find_node(menu, "Test MM Catalog")
		self.assertEqual(catalog["item_groups"], ["Test MM Catalog"])
		level_2 = catalog["children"][0]
		level_3 = level_2["children"][0]
		self.assertEqual(level_2["label"], "Test MM Level 2")
		self.assertEqual(level_3["label"], "Test MM Level 3")
		self.assertEqual(level_3["children"], [])
		self.assertFalse(frappe.db.exists("Ecommerce Category", {"display_name": "Test MM Level 4"}))

		self.assertEqual(before, self.item_group_snapshot())

	def test_importing_twice_adds_nothing(self):
		self.make_deep_item_group_tree()
		navbar_manager.import_from_item_group(item_group="Test MM Catalog")
		after_first = sorted(self.imported_names())
		before = self.item_group_snapshot()

		navbar_manager.import_from_item_group(item_group="Test MM Catalog")

		self.assertEqual(after_first, sorted(self.imported_names()))
		self.assertEqual(before, self.item_group_snapshot())

	def test_import_grafts_under_an_existing_entry(self):
		self.make_deep_item_group_tree()

		menu = navbar_manager.import_from_item_group(item_group="Test MM Catalog", parent=self.men)["menu"]

		catalog = find_node(menu, "Test MM Men - Test MM Catalog")
		self.assertEqual(catalog["parent"], self.men)
		# Grafting one level down costs the deepest source level its place.
		self.assertEqual(catalog["children"][0]["children"], [])
		self.assertTrue(frappe.db.get_value("Ecommerce Category", self.men, "is_group"))

	def test_import_leaves_the_nested_set_consistent(self):
		self.make_deep_item_group_tree()
		navbar_manager.import_from_item_group(item_group="Test MM Catalog")

		bounds = self.tree_bounds()
		rebuild_tree("Ecommerce Category")
		self.assertEqual(bounds, self.tree_bounds())

		# A normal edit still works on top of a bulk-imported branch.
		child = self.add_node("Test MM Catalog", "Test MM Hand Made")
		navbar_manager.move_node(child["name"], self.men, 0)
		self.assertEqual(
			frappe.db.get_value("Ecommerce Category", child["name"], "parent_ecommerce_category"), self.men
		)
		bounds = self.tree_bounds()
		rebuild_tree("Ecommerce Category")
		self.assertEqual(bounds, self.tree_bounds())

	def tree_bounds(self):
		return frappe.get_all(
			"Ecommerce Category", fields=["name", "lft", "rgt"], order_by="name asc", limit_page_length=0
		)

	def test_route_slug_is_required_on_roots_only(self):
		child = self.add_node(self.men, "Test MM Accessories")

		self.assertEqual(frappe.db.get_value("Ecommerce Category", self.men, "route_slug"), "test_mm_men")
		self.assertFalse(frappe.db.get_value("Ecommerce Category", child["name"], "route_slug"))

	def display_and_seo_values(self, name):
		return frappe.db.get_value(
			"Ecommerce Category",
			name,
			["icon", "image", "meta_title", "meta_description", "og_image", "noindex"],
			as_dict=True,
		)

	def display_and_seo_node_values(self, menu, name):
		node = find_node(menu, name)
		return {
			field: node[field]
			for field in ("icon", "image", "meta_title", "meta_description", "og_image", "noindex")
		}

	def test_update_node_writes_display_and_seo_fields(self):
		navbar_manager.update_node(
			self.men,
			icon="bag",
			image="https://cdn.example.com/men.png",
			meta_title="Test MM Menswear",
			meta_description="Test MM shirts and shoes",
			og_image="https://cdn.example.com/men-og.png",
			noindex=1,
		)

		self.assertEqual(
			self.display_and_seo_values(self.men),
			{
				"icon": "bag",
				"image": "https://cdn.example.com/men.png",
				"meta_title": "Test MM Menswear",
				"meta_description": "Test MM shirts and shoes",
				"og_image": "https://cdn.example.com/men-og.png",
				"noindex": 1,
			},
		)

	def test_update_node_leaves_display_and_seo_fields_alone_when_omitted(self):
		navbar_manager.update_node(self.men, icon="bag", meta_title="Test MM Menswear", noindex=1)

		navbar_manager.update_node(self.men, display_name="Test MM Mens")

		self.assertEqual(
			self.display_and_seo_values(self.men),
			{
				"icon": "bag",
				"image": None,
				"meta_title": "Test MM Menswear",
				"meta_description": None,
				"og_image": None,
				"noindex": 1,
			},
		)

	def test_update_node_clears_display_and_seo_fields_on_blank(self):
		navbar_manager.update_node(self.men, icon="bag", meta_title="Test MM Menswear", noindex=1)

		navbar_manager.update_node(self.men, icon="", meta_title="", noindex=0)

		self.assertEqual(
			self.display_and_seo_values(self.men),
			{
				"icon": "",
				"image": None,
				"meta_title": "",
				"meta_description": None,
				"og_image": None,
				"noindex": 0,
			},
		)

	def test_menu_payload_carries_the_display_and_seo_fields(self):
		"""The editor reads these back off the menu it just got, so writing them is only half a contract."""
		menu = navbar_manager.update_node(
			self.men,
			icon="bag",
			image="https://cdn.example.com/men.png",
			meta_title="Test MM Menswear",
			meta_description="Test MM shirts and shoes",
			og_image="https://cdn.example.com/men-og.png",
			noindex=1,
		)["menu"]

		self.assertEqual(
			self.display_and_seo_node_values(menu, self.men),
			{
				"icon": "bag",
				"image": "https://cdn.example.com/men.png",
				"meta_title": "Test MM Menswear",
				"meta_description": "Test MM shirts and shoes",
				"og_image": "https://cdn.example.com/men-og.png",
				"noindex": 1,
			},
		)

		# A cleared checkbox has to survive as the int 0, not as the "" the string fields use.
		menu = navbar_manager.update_node(self.men, noindex=0)["menu"]
		self.assertEqual(find_node(menu, self.men)["noindex"], 0)
		self.assertEqual(find_node(menu, self.men)["meta_title"], "Test MM Menswear")

	def test_update_node_writes_the_description_and_the_editor_reads_it_back(self):
		menu = navbar_manager.update_node(self.men, description="Test MM shirts for every day")["menu"]

		self.assertEqual(find_node(menu, self.men)["description"], "Test MM shirts for every day")
		navbar_manager.update_node(self.men, meta_title="Test MM Menswear")
		self.assertEqual(
			frappe.db.get_value("Ecommerce Category", self.men, "description"), "Test MM shirts for every day"
		)

	def test_update_node_keeps_the_other_fields_when_only_seo_changes(self):
		bags = self.add_node(None, "Test MM Bags", "Item Group", ["Test MM Bags"])

		menu = navbar_manager.update_node(bags["name"], meta_title="Test MM Bags Page")["menu"]

		node = find_node(menu, bags["name"])
		self.assertEqual(node["item_groups"], ["Test MM Bags"])
		self.assertEqual(node["label"], "Test MM Bags")
		self.assertEqual(node["link_type"], "Item Group")
		self.assertEqual(node["route_slug"], "test_mm_bags")


PUBLISH_TEST_INDEX_NAME = "test_commera_navbar_publish.db"
PUBLISH_PREFIX = "ZZ Pub"
PUBLISH_ITEM_ATTRIBUTE = "ZZ Pub Color"
PUBLISH_STYLE_ITEM = "ZZ-PUB-STYLE"


class TestNavbarPublishCascade(IntegrationTestCase):
	"""set_published moves catalogue products, not menu visibility — a different axis from set_visibility."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.original_index_name = SqliteProductSearch.INDEX_NAME
		cls.original_indexable = SqliteProductSearch.INDEXABLE_DOCTYPES
		SqliteProductSearch.INDEX_NAME = PUBLISH_TEST_INDEX_NAME
		SqliteProductSearch().drop_index()

		cls.build_catalogue()
		cls.build_menu()
		cls.scope_index_to_fixtures()

	@classmethod
	def tearDownClass(cls):
		SqliteProductSearch().drop_index()
		SqliteProductSearch.INDEX_NAME = cls.original_index_name
		SqliteProductSearch.INDEXABLE_DOCTYPES = cls.original_indexable
		delete_menu_entries({"name": ["like", f"{PUBLISH_PREFIX}%"]})
		super().tearDownClass()

	def setUp(self):
		clear_search_engine()
		frappe.db.set_value(
			"Style Attribute Variant",
			{"name": ["in", [self.dress, self.gown, self.shoe, self.incomplete]]},
			{"is_published": 0},
		)
		frappe.db.set_value("Style Attribute Variant", self.bag, "is_published", 1)

	@classmethod
	def build_catalogue(cls):
		"""Two item-group arms: Dresses (with a child group) + Footwear under Women, Luggage outside."""
		cls.make_group("ZZ Pub Dresses", is_group=1)
		cls.make_group("ZZ Pub Gowns", parent="ZZ Pub Dresses")
		cls.make_group("ZZ Pub Footwear")
		cls.make_group("ZZ Pub Luggage")
		cls.make_group("ZZ Pub Items")

		if not frappe.db.exists("Item Attribute", PUBLISH_ITEM_ATTRIBUTE):
			frappe.get_doc(
				{
					"doctype": "Item Attribute",
					"attribute_name": PUBLISH_ITEM_ATTRIBUTE,
					"item_attribute_values": [{"attribute_value": "ZZ Pub Red", "abbr": "ZPR"}],
				}
			).insert(ignore_permissions=True)

		cls.make_item(PUBLISH_STYLE_ITEM, "ZZ Pub Style Template")
		cls.configurator = (
			frappe.get_doc(
				{
					"doctype": "Style Attribute Configurator",
					"item_template": PUBLISH_STYLE_ITEM,
					"item_attribute": PUBLISH_ITEM_ATTRIBUTE,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

		cls.dress = cls.make_variant("ZZ Pub Dress", "ZZ Pub Dresses", is_published=0)
		cls.gown = cls.make_variant("ZZ Pub Gown", "ZZ Pub Gowns", is_published=0)
		cls.shoe = cls.make_variant("ZZ Pub Shoe", "ZZ Pub Footwear", is_published=0)
		cls.bag = cls.make_variant("ZZ Pub Bag", "ZZ Pub Luggage", is_published=1)
		# No images: unpublish_if_incomplete_data would revert a publish, so the cascade must skip it.
		cls.incomplete = cls.make_variant("ZZ Pub Draft", "ZZ Pub Dresses", is_published=0, images=False)

		# publish expands every linked group over its Item Group descendants, so the child gown is reached.
		cls.cascaded = [cls.dress, cls.gown, cls.shoe]

	@classmethod
	def make_group(cls, name, parent=None, is_group=0):
		if frappe.db.exists("Item Group", name):
			return
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": name,
				"custom_displayname": name,
				"is_group": is_group,
				"parent_item_group": parent or get_root_of("Item Group"),
			}
		).insert(ignore_permissions=True)

	@classmethod
	def make_item(cls, item_code, item_name):
		if frappe.db.exists("Item", item_code):
			return
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_name,
				"item_group": "ZZ Pub Items",
				"stock_uom": "Nos",
				"is_stock_item": 1,
			}
		).insert(ignore_permissions=True)

	@classmethod
	def make_variant(cls, display_name, item_group, is_published, images=True):
		item_code = f"{display_name.replace(' ', '-')}-S"
		cls.make_item(item_code, display_name)
		variant = {
			"doctype": "Style Attribute Variant",
			"configurator": cls.configurator,
			"item_style": PUBLISH_STYLE_ITEM,
			"attribute_name": display_name,
			"attribute_value": display_name,
			"display_name": display_name,
			"item_group": item_group,
			"is_published": is_published,
			"sizes": [{"size": "S", "item_code": item_code}],
		}
		if images:
			variant["images"] = [{"image": "/files/zz-pub.png"}]
		return frappe.get_doc(variant).insert(ignore_permissions=True).name

	@classmethod
	def build_menu(cls):
		cls.women = navbar_manager.create_node("", "ZZ Pub Women", "Item Group", ["ZZ Pub Dresses"]).name
		cls.footwear = navbar_manager.create_node(
			cls.women, "ZZ Pub Footwear", "Item Group", ["ZZ Pub Footwear"]
		).name
		cls.men = navbar_manager.create_node("", "ZZ Pub Men", "Item Group", ["ZZ Pub Luggage"]).name
		cls.heading = navbar_manager.create_node("", "ZZ Pub Heading").name

	@classmethod
	def scope_index_to_fixtures(cls):
		"""Keep the test index to these five variants so a build stays fast and assertions stay exact."""
		scoped = copy.deepcopy(SqliteProductSearch.INDEXABLE_DOCTYPES)
		scoped["Style Attribute Variant"]["filters"] = {
			"is_published": 1,
			"name": ("in", [cls.dress, cls.gown, cls.shoe, cls.bag, cls.incomplete]),
		}
		scoped["Ecommerce Category"]["filters"] = {"enabled": 1, "name": ("in", ["ZZ Pub No Category"])}
		SqliteProductSearch.INDEXABLE_DOCTYPES = scoped

	def published_variants(self):
		return sorted(
			frappe.get_all(
				"Style Attribute Variant",
				filters={
					"name": ["in", [self.dress, self.gown, self.shoe, self.bag, self.incomplete]],
					"is_published": 1,
				},
				pluck="name",
			)
		)

	def item_group_snapshot(self):
		return frappe.get_all(
			"Item Group", fields=ITEM_GROUP_SNAPSHOT_FIELDS, order_by="name asc", limit_page_length=0
		)

	def set_published_now(self, name, publish):
		"""set_published with the index job run inline, since a test rolls back before after_commit."""
		with patch.object(bulk_publish_variants, "enqueue_upsert_many", side_effect=sync.upsert_docs) as job:
			result = navbar_manager.set_published(name, publish)
		return result, job

	def indexed_variants(self):
		engine = SqliteProductSearch()
		names = [self.dress, self.gown, self.shoe, self.bag, self.incomplete]
		return sorted(card["name"] for card in engine.hydrate_cards(names))

	def test_publish_reaches_descendant_nodes_and_descendant_item_groups(self):
		self.set_published_now(self.women, 1)

		self.assertEqual(self.published_variants(), sorted([*self.cascaded, self.bag]))
		self.assertTrue(frappe.db.get_value("Style Attribute Variant", self.gown, "is_published"))

	def test_preview_count_matches_what_set_published_changes(self):
		preview = navbar_manager.get_publish_preview(self.women, 1)
		self.assertEqual(preview, {"count": 3, "label": "ZZ Pub Women"})

		result, _job = self.set_published_now(self.women, 1)
		self.assertEqual(result["count"], 3)

		# Nothing left to move, so the honest count is now zero on both sides.
		self.assertEqual(navbar_manager.get_publish_preview(self.women, 1)["count"], 0)
		self.assertEqual(self.set_published_now(self.women, 1)[0]["count"], 0)

	def test_unpublish_is_the_exact_inverse_of_publish(self):
		before = self.published_variants()

		self.set_published_now(self.women, 1)
		self.assertNotEqual(self.published_variants(), before)

		result, _job = self.set_published_now(self.women, 0)
		self.assertEqual(self.published_variants(), before)
		self.assertEqual(result["count"], 3)

	def test_publish_skips_products_missing_images_or_sizes(self):
		self.set_published_now(self.women, 1)

		self.assertFalse(frappe.db.get_value("Style Attribute Variant", self.incomplete, "is_published"))

	def test_a_node_outside_the_branch_is_untouched(self):
		self.set_published_now(self.women, 0)

		self.assertTrue(frappe.db.get_value("Style Attribute Variant", self.bag, "is_published"))

	def test_node_without_a_linked_item_group_is_a_safe_no_op(self):
		before = self.published_variants()

		self.assertEqual(navbar_manager.get_publish_preview(self.heading, 1)["count"], 0)
		result, job = self.set_published_now(self.heading, 1)

		self.assertEqual(result["count"], 0)
		self.assertEqual(self.published_variants(), before)
		job.assert_called_once_with("Style Attribute Variant", [])

	def test_publish_cascade_never_touches_item_group(self):
		before = self.item_group_snapshot()

		self.set_published_now(self.women, 1)
		self.set_published_now(self.women, 0)

		self.assertEqual(before, self.item_group_snapshot())

	def test_set_published_returns_the_refreshed_menu(self):
		result, _job = self.set_published_now(self.women, 1)

		self.assertEqual(find_node(result["menu"], self.footwear)["label"], "ZZ Pub Footwear")

	def test_unknown_node_throws(self):
		with self.assertRaises(frappe.ValidationError):
			navbar_manager.get_publish_preview("ZZ Pub Nope", 1)

	def test_storefront_index_follows_the_cascade(self):
		self.set_published_now(self.women, 1)
		engine = SqliteProductSearch()
		engine.drop_index()
		engine.build_index()
		clear_search_engine()
		self.assertEqual(self.indexed_variants(), sorted([*self.cascaded, self.bag]))

		self.set_published_now(self.women, 0)
		self.assertEqual(self.indexed_variants(), [self.bag])

		self.set_published_now(self.women, 1)
		self.assertEqual(self.indexed_variants(), sorted([*self.cascaded, self.bag]))

	def test_the_bulk_publish_tool_shares_the_publish_path(self):
		"""Bulk Publish Variants had no index sync at all, so it left ghosts the storefront kept serving."""
		tool = frappe.get_single("Bulk Publish Variants")
		tool.vendor_code = tool.dcs = tool.brand = tool.item_code = tool.season_code = None

		with patch.object(bulk_publish_variants, "enqueue_upsert_many", side_effect=sync.upsert_docs) as job:
			result = tool.bulk_toggle_publish(
				publish=1, style_attribute_variant_list=[self.dress, self.incomplete]
			)

		self.assertEqual(result, {"updated_count": 1, "total_matched": 2})
		job.assert_called_once_with("Style Attribute Variant", [self.dress])
		self.assertFalse(frappe.db.get_value("Style Attribute Variant", self.incomplete, "is_published"))

	def test_publishing_a_named_set_ignores_filters_left_on_the_bulk_publish_form(self):
		"""The Item tab's "Publish all ready" sends an explicit list, and it must publish that list.

		`bulk_toggle_publish` ANDs the Single's stored filters in, so a stale `brand` silently empties the set.
		"""
		tool = frappe.get_single("Bulk Publish Variants")
		tool.vendor_code = tool.dcs = tool.brand = tool.season_code = None
		# A leftover filter, exactly as it would sit on the form between two uses of the tool.
		tool.item_code = "ZZ-PUB-NO-SUCH-ITEM"

		# The old path: the stale filter matches nothing, so the explicit selection is lost.
		with patch.object(bulk_publish_variants, "enqueue_upsert_many", side_effect=sync.upsert_docs):
			filtered = tool.bulk_toggle_publish(publish=1, style_attribute_variant_list=[self.dress])
		self.assertEqual(filtered["updated_count"], 0)
		self.assertFalse(frappe.db.get_value("Style Attribute Variant", self.dress, "is_published"))

		# The endpoint the tab actually calls takes the names and no other criteria.
		with patch.object(bulk_publish_variants, "enqueue_upsert_many", side_effect=sync.upsert_docs) as job:
			result = bulk_publish_variants.set_variants_published(1, [self.dress, self.incomplete])

		self.assertEqual(result, {"updated_count": 1})
		job.assert_called_once_with("Style Attribute Variant", [self.dress])
		self.assertTrue(frappe.db.get_value("Style Attribute Variant", self.dress, "is_published"))
		# The completeness gate still applies — an explicit list is not a licence to publish a draft.
		self.assertFalse(frappe.db.get_value("Style Attribute Variant", self.incomplete, "is_published"))

	def test_set_published_hands_the_changed_names_to_the_index_job(self):
		_result, job = self.set_published_now(self.women, 1)

		job.assert_called_once()
		doctype, names = job.call_args.args
		self.assertEqual(doctype, "Style Attribute Variant")
		self.assertEqual(sorted(names), sorted(self.cascaded))
