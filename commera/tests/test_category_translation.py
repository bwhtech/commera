import frappe
from frappe.tests import IntegrationTestCase

from commera.localization import get_translatable_fields, register
from commera.sdk import catalog, shop
from commera.shop_data import find_menu_root, get_category_facets, get_storefront_menu
from commera.tests.test_content_translation import use_storefront_language
from commera.tests.test_localization import set_storefront_languages
from commera.themes.commera_starter.pages.products import details
from commera.themes.commera_starter.pages.products.list import add_seo
from commera.www.products.list import apply_category_scope

CATEGORY = "Ecommerce Category"


class TestCategoryTranslation(IntegrationTestCase):
	def setUp(self):
		set_storefront_languages("en", published=("en", "ar"))
		self.addCleanup(frappe.clear_document_cache, "Commera Settings", "Commera Settings")
		self.tab = self.make_category(
			"Tab", is_group=1, description="Tab story", meta_title="Tab title", meta_description="Tab text"
		)
		self.entry = self.make_category("Entry", parent=self.tab.name)
		register(CATEGORY, self.tab.name, "display_name", "ar", "رجال")
		register(CATEGORY, self.tab.name, "description", "ar", "قصة الرجال")
		register(CATEGORY, self.tab.name, "meta_title", "ar", "ملابس الرجال")
		register(CATEGORY, self.tab.name, "meta_description", "ar", "تسوق ملابس الرجال")
		register(CATEGORY, self.entry.name, "display_name", "ar", "قمصان")

	def make_category(self, label, parent=None, **values):
		category = frappe.get_doc(
			{
				"doctype": CATEGORY,
				"category_name": f"{label} {frappe.generate_hash(length=8)}",
				"parent_ecommerce_category": parent,
				"enabled": 1,
				**values,
			}
		).insert(ignore_permissions=True)
		return category

	def serve(self, language):
		use_storefront_language(self, language)
		frappe.local.commera_storefront_menu = None
		self.addCleanup(setattr, frappe.local, "commera_storefront_menu", None)

	def menu_tab(self):
		return next(item for item in shop.get_shop()["menu"] if item["target"] == self.tab.route_slug)

	def test_the_registry_declares_the_category_name_and_seo_fields(self):
		self.assertEqual(
			get_translatable_fields(CATEGORY),
			{"display_name", "description", "meta_title", "meta_description"},
		)

	def test_a_collection_shows_its_translated_title_and_seo(self):
		self.serve("ar")
		collection = catalog.get_collection(self.tab.route_slug)

		self.assertEqual((collection["title"], collection["description"]), ("رجال", "قصة الرجال"))
		self.assertEqual(
			collection["seo"],
			{
				"title": "ملابس الرجال",
				"custom_title": True,
				"description": "تسوق ملابس الرجال",
				"noindex": False,
			},
		)
		listed = next(c for c in catalog.list_collections() if c["handle"] == self.tab.route_slug)
		self.assertEqual((listed["title"], listed["description"]), ("رجال", "قصة الرجال"))

	def test_the_default_language_shows_the_source(self):
		self.serve("en")
		collection = catalog.get_collection(self.tab.route_slug)

		self.assertEqual(collection["title"], self.tab.display_name)
		self.assertEqual(collection["description"], "Tab story")
		self.assertEqual(collection["seo"]["title"], "Tab title")
		self.assertEqual(self.menu_tab()["items"][0]["title"], self.entry.display_name)

	def test_the_menu_shows_translated_labels_at_every_level(self):
		self.serve("ar")
		tab = self.menu_tab()

		self.assertEqual((tab["title"], tab["items"][0]["title"]), ("رجال", "قمصان"))
		root = next(node for node in get_storefront_menu() if node["name"] == self.tab.name)
		self.assertEqual(
			(root["meta_title"], root["meta_description"]), ("ملابس الرجال", "تسوق ملابس الرجال")
		)

	def test_an_untranslated_category_falls_back_to_frappe_translation_then_the_source(self):
		frappe_translated = self.make_category("Frappe", parent=self.tab.name)
		untranslated = self.make_category("Plain", parent=self.tab.name)
		translation = frappe.get_doc(
			{
				"doctype": "Translation",
				"language": "ar",
				"source_text": frappe_translated.display_name,
				"translated_text": "من فرابيه",
			}
		).insert()
		self.addCleanup(frappe.delete_doc, "Translation", translation.name, force=True)

		self.serve("ar")
		titles = [item["title"] for item in self.menu_tab()["items"]]

		self.assertEqual(titles, ["قمصان", "من فرابيه", untranslated.display_name])

	def test_the_menu_editor_reads_the_untranslated_tree(self):
		from commera.commera_ecommerce.doctype.ecommerce_category.ecommerce_category import get_menu_tree

		self.serve("ar")
		get_storefront_menu()
		root = next(node for node in get_menu_tree() if node["name"] == self.tab.name)

		self.assertEqual(root["label"], self.tab.display_name)

	def test_the_listing_sidebar_and_collection_seo_use_the_translation(self):
		self.serve("ar")
		self.assertIn("رجال", get_category_facets(self.tab.route_slug))

		context = frappe._dict(
			query="", collection=catalog.get_collection(self.tab.route_slug), listing={"total": 3}
		)
		add_seo(context)
		self.assertEqual(context.seo["title"], "ملابس الرجال")
		self.assertEqual(context.seo["description"], "تسوق ملابس الرجال")

	def test_deleting_a_category_deletes_its_translations(self):
		entry = self.entry.name
		frappe.delete_doc(CATEGORY, entry)

		self.assertFalse(
			frappe.db.exists("Content Translation", {"reference_doctype": CATEGORY, "reference_name": entry})
		)

	def test_a_source_label_category_link_keeps_filtering_in_every_language(self):
		for language in ("en", "ar"):
			with self.subTest(language=language):
				self.serve(language)
				self.assertEqual(
					find_menu_root(get_storefront_menu(), self.tab.display_name)["name"], self.tab.name
				)

				selected = {"category": self.tab.display_name}
				self.assertEqual(apply_category_scope(selected)["name"], self.tab.name)
				self.assertEqual(selected["category"], self.tab.display_name)
				self.assertIn("category_item_groups", selected)
				self.assertTrue(get_category_facets(self.tab.display_name))

	def test_a_translated_label_is_no_category_identifier(self):
		self.serve("ar")
		self.assertIsNone(find_menu_root(get_storefront_menu(), "رجال"))

	def test_a_category_without_a_description_has_an_empty_one(self):
		self.serve("ar")
		self.assertEqual(catalog.get_collection(self.make_category("Bare").route_slug)["description"], "")

	def test_a_meta_title_equal_to_the_collection_title_is_kept(self):
		self.serve("en")
		tab = self.make_category("Same")
		tab.db_set("meta_title", tab.display_name)

		self.assertEqual(self.collection_seo_title(tab), tab.display_name)

	def test_a_collection_without_a_meta_title_uses_the_title_template(self):
		self.serve("en")
		tab = self.make_category("Untitled")

		self.assertEqual(catalog.get_collection(tab.route_slug)["seo"]["custom_title"], False)
		self.assertTrue(self.collection_seo_title(tab).startswith(f"{tab.display_name} | "))

	def test_a_product_meta_title_equal_to_the_product_title_is_kept(self):
		context = frappe._dict(breadcrumb_links=[{"label": "Shoes"}])
		product = {
			"id": "SHOES",
			"handle": "shoes",
			"title": "Shoes",
			"selected_variant_id": None,
			"vendor": None,
			"description_html": "",
			"images": [],
			"price": 10,
			"available": True,
			"currency": "USD",
			"rating": {"count": 0, "average": 0},
			"seo": catalog.get_seo("Shoes", "Shoes", None, 0),
		}
		details.add_seo(context, product)

		self.assertEqual(context.seo["title"], "Shoes")

	def collection_seo_title(self, category):
		context = frappe._dict(
			query="", collection=catalog.get_collection(category.route_slug), listing={"total": 1}
		)
		add_seo(context)
		return context.seo["title"]
