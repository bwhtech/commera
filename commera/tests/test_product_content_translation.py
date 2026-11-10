import frappe

from commera.localization import (
	CURRENT,
	MISSING,
	OUTDATED,
	get_translatable_fields,
	register,
	resolve,
	translate,
)
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
			return translate([frappe.get_doc(PRODUCT, product.name)], ["description"], arabic)[0][
				"description"
			].status

		self.assertEqual(status(), CURRENT)
		frappe.db.set_value("Item", product.item_style, "description", "<p>A linen shirt, now longer.</p>")
		self.assertEqual(status(), OUTDATED)
		self.assertEqual(self.get_product(product, "ar")["description_html"], "<p>قميص كتان.</p>")

	def test_a_product_document_translates_its_items_description(self):
		products = [self.make_product(label) for label in ("DOC-A", "DOC-B", "DOC-C")]
		register(PRODUCT, products[0].name, "description", "ar", "<p>قميص كتان.</p>")
		docs = [frappe.get_doc(PRODUCT, product.name) for product in products]
		arabic, english = resolve("/ar")[0], resolve("/en")[0]
		translate(docs, ["description"], arabic)

		# One query reads every Item description, one reads every translation.
		with self.assertQueryCount(2):
			translated = translate(docs, ["description"], arabic)

		self.assertEqual(
			[(value["description"].value, value["description"].status) for value in translated],
			[("<p>قميص كتان.</p>", CURRENT), (DESCRIPTION, MISSING), (DESCRIPTION, MISSING)],
		)
		self.assertEqual(translate(docs[1:2], ["description"], english)[0]["description"].value, DESCRIPTION)

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
		colour_sources = {value["handle"]: value["value"] for value in colour["values"]}
		self.assertEqual(colour_sources[products[0].route], products[0].attribute_value)
		self.assertEqual(self.get_product(products[0], "ar")["color"], "أحمر")
		self.assertEqual(catalog.get_product_cards_for([products[0].name])[0]["color"], "أحمر")

	def test_sizes_that_share_a_translated_label_keep_their_own_source_value(self):
		product = self.make_product("SAME-LABEL")
		medium = self.make_item("SAME-LABEL-MEDIUM")
		self.make_item_price(medium, self.default_price_list, 30)
		doc = frappe.get_doc(PRODUCT, product.name)
		doc.append("sizes", {"size": "Medium", "item_code": medium})
		doc.save(ignore_permissions=True)
		self.add_frappe_translation("M", "وسط")
		self.add_frappe_translation("Medium", "وسط")

		page = self.get_product(product, "ar")

		size = next(
			option for option in page["options"] if option["values"] and "handle" not in option["values"][0]
		)
		self.assertEqual(
			[(value["name"], value["value"]) for value in size["values"]], [("وسط", "M"), ("وسط", "Medium")]
		)
		self.assertEqual(
			[(variant["title"], variant["size"], variant["id"]) for variant in page["variants"]],
			[("وسط", "M", product.sizes[0].item_code), ("وسط", "Medium", medium)],
		)

	def test_untranslated_option_terms_keep_their_source(self):
		product = self.make_product("OPTIONS-SOURCE")

		page = self.get_product(product, "ar")

		self.assertEqual(page["color"], product.attribute_value)
		self.assertEqual(page["variants"][0]["title"], "M")
