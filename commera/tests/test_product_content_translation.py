import frappe

from commera.localization import CURRENT, OUTDATED, get_translatable_fields, register, resolve, translate
from commera.sdk import catalog
from commera.tests.test_content_translation import use_storefront_language
from commera.tests.test_localization import set_storefront_languages
from commera.tests.test_product_details import ProductDetailPriceTestCase

PRODUCT = "Style Attribute Variant"
DESCRIPTION = "<p>A linen shirt for warm days.</p>"


class TestProductContentTranslation(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		set_storefront_languages("en", published=("en", "ar"))

	def make_product(self, label, **fields):
		route = self.make_priced_variant(label, default_rate=30)
		product = frappe.get_doc(PRODUCT, {"route": route})
		frappe.db.set_value("Item", product.item_style, "description", DESCRIPTION)
		if fields:
			frappe.db.set_value(PRODUCT, product.name, fields)
		return product

	def add_frappe_translation(self, source, translated):
		translation = frappe.get_doc(
			{"doctype": "Translation", "language": "ar", "source_text": source, "translated_text": translated}
		).insert()
		self.addCleanup(frappe.delete_doc, "Translation", translation.name, force=True)

	def get_product(self, product, language):
		use_storefront_language(self, language)
		return catalog.get_product(product.route)

	def test_the_registry_declares_the_description_and_seo_fields(self):
		self.assertTrue(
			{"display_name", "description", "meta_title", "meta_description"}
			<= get_translatable_fields(PRODUCT)
		)

	def test_the_product_page_shows_the_translated_description(self):
		product = self.make_product("DESCRIPTION")
		register(PRODUCT, product.name, "description", "ar", "<p>قميص كتان للأيام الدافئة.</p>")

		self.assertEqual(
			self.get_product(product, "ar")["description_html"], "<p>قميص كتان للأيام الدافئة.</p>"
		)
		self.assertEqual(self.get_product(product, "en")["description_html"], DESCRIPTION)

	def test_a_description_translation_is_current_against_the_items_description(self):
		product = self.make_product("DESCRIPTION-HASH")
		register(PRODUCT, product.name, "description", "ar", "<p>قميص كتان.</p>")
		arabic = resolve("/ar")[0]

		def status():
			source = {
				"name": product.name,
				"description": frappe.db.get_value("Item", product.item_style, "description"),
			}
			return translate([source], ["description"], arabic, doctype=PRODUCT)[0]["description"].status

		self.assertEqual(status(), CURRENT)
		frappe.db.set_value("Item", product.item_style, "description", "<p>A linen shirt, now longer.</p>")
		self.assertEqual(status(), OUTDATED)
		self.assertEqual(self.get_product(product, "ar")["description_html"], "<p>قميص كتان.</p>")

	def test_the_product_seo_title_and_description_are_translated(self):
		product = self.make_product("SEO", meta_title="Linen shirt | Shop", meta_description="Cool linen.")
		register(PRODUCT, product.name, "meta_title", "ar", "قميص كتان | المتجر")
		register(PRODUCT, product.name, "meta_description", "ar", "كتان بارد.")

		seo = self.get_product(product, "ar")["seo"]
		self.assertEqual((seo["title"], seo["description"]), ("قميص كتان | المتجر", "كتان بارد."))
		seo = self.get_product(product, "en")["seo"]
		self.assertEqual((seo["title"], seo["description"]), ("Linen shirt | Shop", "Cool linen."))

	def test_without_a_meta_title_the_seo_title_is_the_translated_title(self):
		product = self.make_product("SEO-TITLE")
		register(PRODUCT, product.name, "display_name", "ar", "قميص الكتان")

		self.assertEqual(self.get_product(product, "ar")["seo"]["title"], "قميص الكتان")

	def test_untranslated_content_falls_back_to_frappe_translation_then_the_source(self):
		product = self.make_product(
			"FALLBACK", meta_title="Linen shirt | Shop", meta_description="Cool linen."
		)
		self.add_frappe_translation("Cool linen.", "كتان بارد من فرابيه")

		page = self.get_product(product, "ar")

		self.assertEqual(page["description_html"], DESCRIPTION)
		self.assertEqual(page["seo"]["title"], "Linen shirt | Shop")
		self.assertEqual(page["seo"]["description"], "كتان بارد من فرابيه")

	def test_one_frappe_translation_covers_an_option_term_on_every_product(self):
		products = [self.make_product(label) for label in ("OPTIONS-A", "OPTIONS-B")]
		attribute = frappe.db.get_value(
			"Style Attribute Configurator", products[0].configurator, "item_attribute"
		)
		self.add_frappe_translation(attribute, "السمة")
		self.add_frappe_translation("M", "وسط")
		self.add_frappe_translation(products[0].attribute_value, "أحمر")

		for product in products:
			page = self.get_product(product, "ar")
			colour, size = page["options"]
			self.assertEqual(colour["name"], "السمة")
			self.assertEqual([value["name"] for value in size["values"]], ["وسط"])
			self.assertEqual(page["variants"][0]["title"], "وسط")

		colour_values = {value["handle"]: value["name"] for value in colour["values"]}
		self.assertEqual(colour_values[products[0].route], "أحمر")
		self.assertEqual(self.get_product(products[0], "ar")["color"], "أحمر")
		self.assertEqual(catalog.get_product_cards_for([products[0].name])[0]["color"], "أحمر")

	def test_untranslated_option_terms_keep_their_source(self):
		product = self.make_product("OPTIONS-SOURCE")

		page = self.get_product(product, "ar")

		self.assertEqual(page["color"], product.attribute_value)
		self.assertEqual(page["variants"][0]["title"], "M")
