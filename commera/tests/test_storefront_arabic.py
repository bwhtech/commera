import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from commera.api.storefront.shop import get_translations
from commera.sdk import catalog, shop
from commera.sdk.catalog import get_line_products
from commera.sdk.shop import get_menu_item
from commera.tests.test_product_details import ProductDetailPriceTestCase

ARABIC_FIELDS = {"custom_item_name_ar": "Data", "custom_description_ar": "Text Editor"}
ARABIC_NAME = "فرامل أمامية"


class TestStorefrontArabic(ProductDetailPriceTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Commera reads these site fields but does not create them. The DDL commits, so it is made once here.
		cls.created_fields = [
			fieldname for fieldname in ARABIC_FIELDS if not frappe.db.has_column("Item", fieldname)
		]
		create_custom_fields(
			{
				"Item": [
					{"fieldname": fieldname, "fieldtype": ARABIC_FIELDS[fieldname], "label": fieldname}
					for fieldname in cls.created_fields
				]
			},
			ignore_validate=True,
		)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		frappe.db.rollback()
		for fieldname in cls.created_fields:
			frappe.delete_doc("Custom Field", f"Item-{fieldname}", ignore_missing=True, force=True)
		frappe.db.commit()

	def setUp(self):
		super().setUp()
		self.addCleanup(setattr, frappe.local, "lang", "en")
		self.collection = self.make_collection()
		self.route = self.make_priced_variant("ARABIC", default_rate=40)
		self.variant = frappe.get_doc("Style Attribute Variant", {"route": self.route})
		frappe.db.set_value(
			"Item",
			self.variant.item_style,
			{
				"custom_item_name_ar": ARABIC_NAME,
				"description": "<p>Front brake pads</p>",
				"custom_description_ar": "<p>وسادات الفرامل</p>",
			},
		)

	def make_collection(self) -> str:
		category = frappe.new_doc("Ecommerce Category")
		category.category_name = f"Arabic Tab {frappe.generate_hash(length=8)}"
		category.enabled = 1
		category.link_type = "Item Group"
		category.append("link_item_groups", {"item_group": self.item_group})
		category.insert(ignore_permissions=True)
		frappe.local.commera_storefront_menu = None
		self.addCleanup(setattr, frappe.local, "commera_storefront_menu", None)
		self.collection_title = category.display_name or category.category_name
		return category.route_slug

	def make_variant(self, item_code: str, route: str):
		# The configurator gives every product its item style, so each product here gets its own Item.
		variant = super().make_variant(item_code, route)
		variant.db_set("item_style", item_code)
		return variant

	def add_translation(self, source_text: str, translated_text: str):
		frappe.get_doc(
			{
				"doctype": "Translation",
				"language": "ar",
				"source_text": source_text,
				"translated_text": translated_text,
			}
		).insert(ignore_permissions=True)

	def get_card_titles(self) -> dict[str, str]:
		page = catalog.list_products(collection=self.collection)
		return {card["handle"]: card["title"] for card in page["products"]}

	def test_arabic_titles_and_descriptions_fall_back_to_english(self):
		english_only = self.make_priced_variant("ENGLISH", default_rate=40)
		arabic_title = f"{ARABIC_NAME} - {self.variant.attribute_value}"

		english_product = catalog.get_product(self.route)
		english_cards = self.get_card_titles()
		frappe.local.lang = "ar"
		arabic_product = catalog.get_product(self.route)

		self.assertEqual(english_product["title"], self.variant.display_name)
		self.assertEqual(english_product["description_html"], "<p>Front brake pads</p>")
		self.assertEqual(english_cards[self.route], self.variant.display_name)
		self.assertEqual(arabic_product["title"], arabic_title)
		self.assertEqual(arabic_product["description_html"], "<p>وسادات الفرامل</p>")
		self.assertEqual(self.get_card_titles()[self.route], arabic_title)
		self.assertEqual(
			get_line_products([self.variant.item_style])[self.variant.item_style]["title"], arabic_title
		)
		self.assertEqual(catalog.get_product(english_only)["title"], f"Display {english_only}")
		self.assertEqual(self.get_card_titles()[english_only], f"Display {english_only}")

	def test_the_colour_name_is_not_repeated_in_the_arabic_title(self):
		frappe.db.set_value(
			"Item",
			self.variant.item_style,
			"custom_item_name_ar",
			f"{ARABIC_NAME} {self.variant.attribute_value}",
		)
		frappe.local.lang = "ar"

		self.assertEqual(
			catalog.get_product(self.route)["title"], f"{ARABIC_NAME} {self.variant.attribute_value}"
		)

	def test_the_arabic_title_translates_the_colour(self):
		self.add_translation(self.variant.attribute_value, "أحمر")
		frappe.local.lang = "ar"

		self.assertEqual(catalog.get_product(self.route)["title"], f"{ARABIC_NAME} - أحمر")

	def test_arabic_colour_facets_label_the_english_filter_value(self):
		color = self.variant.attribute_value
		self.add_translation(color, "أحمر")
		self.add_translation(self.collection_title, "مجموعة الفرامل")
		collection = self.collection

		english = catalog.list_products(collection=collection)["facets"]["colors"]
		frappe.local.lang = "ar"
		arabic = catalog.list_products(collection=collection)["facets"]["colors"]

		self.assertEqual(english, [{"value": color, "count": 1}])
		self.assertEqual(arabic, [{"value": color, "label": "أحمر", "count": 1}])
		self.assertEqual(catalog.list_products(collection=collection, colors=[color])["total"], 1)
		self.assertEqual(catalog.get_collection(collection)["title"], "مجموعة الفرامل")
		self.assertEqual(catalog.get_product(self.route)["collection"]["title"], "مجموعة الفرامل")

	def test_menu_titles_use_the_site_translation(self):
		label = f"Brakes {self.suffix}"
		self.add_translation(label, "الفرامل")
		node = {"label": label, "link_type": "URL", "url": "/brakes", "parent": "", "children": []}

		self.assertEqual(get_menu_item(node)["title"], label)
		frappe.local.lang = "ar"
		self.assertEqual(get_menu_item(node)["title"], "الفرامل")

	def test_a_page_shows_its_arabic_content_or_else_the_english(self):
		translated = self.make_page("translated", content_ar="<p>مرحبا</p>")
		english_only = self.make_page("english")

		self.assertEqual(shop.get_page(translated)["body_html"], "<p>Hello</p>")
		frappe.local.lang = "ar"
		self.assertEqual(shop.get_page(translated)["body_html"], "<p>مرحبا</p>")
		self.assertEqual(shop.get_page(english_only)["body_html"], "<p>Hello</p>")

	def make_page(self, label: str, content_ar: str | None = None) -> str:
		page = frappe.get_doc(
			{
				"doctype": "Shop Web Page",
				"route": f"{label}-{self.suffix.lower()}",
				"content": "<p>Hello</p>",
				"content_ar": content_ar,
				"published": 1,
			}
		).insert(ignore_permissions=True, set_name=f"{label} {self.suffix}")
		return page.route

	def test_an_arabic_name_finds_its_product(self):
		frappe.local.lang = "ar"

		page = catalog.list_products(query="فرامل")

		self.assertIn(self.route, [card["handle"] for card in page["products"]])

	def test_translations_hold_commera_strings_and_site_records(self):
		self.add_translation("Continue with email", "تابع")
		self.add_translation(f"Label {self.suffix}", "تسمية")

		translations = get_translations("ar")

		self.assertEqual(translations["Sign In"], "تسجيل الدخول")
		self.assertEqual(translations["Continue with email"], "تابع")
		self.assertEqual(translations[f"Label {self.suffix}"], "تسمية")
		# A Frappe string is left out, so the storefront does not download every app's catalog.
		self.assertNotIn("Cancel", translations)
		self.assertNotIn("Sign In", get_translations("en"))

	def test_translations_refuse_a_language_the_storefront_does_not_serve(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Language must be one of"):
			get_translations("fr")
