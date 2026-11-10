from unittest.mock import patch

import frappe
from frappe.translate import get_all_translations

from commera.localization import (
	CURRENT,
	MISSING,
	OUTDATED,
	get_translatable_fields,
	get_translatable_resources,
	register,
	resolve,
	translate,
)
from commera.sdk import catalog
from commera.tests.test_localization import set_storefront_languages
from commera.tests.test_product_details import ProductDetailPriceTestCase

PRODUCT = "Style Attribute Variant"


def use_storefront_language(test_case, code):
	"""Serve the rest of the test like an API request that sends `_lang`."""
	test_case.addCleanup(frappe.local.request_cache.clear)
	test_case.addCleanup(frappe.form_dict.pop, "_lang", None)
	frappe.form_dict["_lang"] = code
	frappe.local.request_cache.clear()


class TestContentTranslation(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		set_storefront_languages("en", published=("en", "ar"))
		self.arabic = resolve("/ar")[0]
		self.english = resolve("/")[0]

	def make_product(self, label):
		route = self.make_priced_variant(label, default_rate=30)
		return frappe.get_doc(PRODUCT, {"route": route})

	def add_frappe_translation(self, source, translated):
		translation = frappe.get_doc(
			{"doctype": "Translation", "language": "ar", "source_text": source, "translated_text": translated}
		).insert()
		self.addCleanup(frappe.delete_doc, "Translation", translation.name, force=True)

	def titles(self, products, localization):
		return [fields["display_name"] for fields in translate(products, ["display_name"], localization)]

	def test_a_content_translation_wins_then_frappe_translation_then_the_source(self):
		translated, frappe_translated, untranslated = (
			self.make_product(label) for label in ("SHOP", "FRAPPE", "NONE")
		)
		register(PRODUCT, translated.name, "display_name", "ar", "قميص الكتان")
		self.add_frappe_translation(frappe_translated.display_name, "قميص من فرابيه")

		titles = self.titles([translated, frappe_translated, untranslated], self.arabic)

		self.assertEqual(
			[title.value for title in titles],
			["قميص الكتان", "قميص من فرابيه", untranslated.display_name],
		)
		self.assertEqual([title.status for title in titles], [CURRENT, MISSING, MISSING])

	def test_the_default_language_reads_the_source(self):
		product = self.make_product("DEFAULT")
		register(PRODUCT, product.name, "display_name", "ar", "قميص الكتان")

		self.assertEqual(self.titles([product], self.english)[0].value, product.display_name)

	def test_editing_the_source_marks_the_translation_outdated_but_still_shows_it(self):
		product = self.make_product("OUTDATED")
		register(PRODUCT, product.name, "display_name", "ar", "قميص الكتان")
		frappe.db.set_value(PRODUCT, product.name, "display_name", f"{product.display_name} v2")
		product.reload()

		title = self.titles([product], self.arabic)[0]
		self.assertEqual((title.value, title.status), ("قميص الكتان", OUTDATED))

		register(PRODUCT, product.name, "display_name", "ar", "قميص الكتان الجديد")
		title = self.titles([product], self.arabic)[0]
		self.assertEqual((title.value, title.status), ("قميص الكتان الجديد", CURRENT))

	def test_a_list_of_records_is_translated_in_one_query_and_keeps_its_order(self):
		products = [self.make_product(label) for label in ("FIRST", "SECOND", "THIRD")]
		for product, title in zip(products, ("الأول", "الثاني", "الثالث"), strict=True):
			register(PRODUCT, product.name, "display_name", "ar", title)
		rows = [{"name": product.name, "display_name": product.display_name} for product in products]

		with self.assertQueryCount(1, query_type=("select",)):
			translated = translate(rows[::-1], ["display_name"], self.arabic, doctype=PRODUCT)

		self.assertEqual(
			[fields["display_name"].value for fields in translated], ["الثالث", "الثاني", "الأول"]
		)

	def test_registering_again_updates_the_one_translation_of_a_field(self):
		product = self.make_product("UPDATE")
		first = register(PRODUCT, product.name, "display_name", "ar", "قميص")
		second = register(PRODUCT, product.name, "display_name", "ar", "قميص الكتان")

		self.assertEqual(first, second)
		self.assertEqual(frappe.db.get_value("Content Translation", first, "translated_value"), "قميص الكتان")
		duplicate = frappe.get_doc("Content Translation", first).as_dict()
		duplicate.pop("name")
		with self.assertRaises(frappe.UniqueValidationError):
			frappe.get_doc(duplicate).insert()

	def test_a_translation_saved_in_desk_is_current_against_the_source(self):
		product = self.make_product("DESK")
		translation = frappe.get_doc(
			{
				"doctype": "Content Translation",
				"reference_doctype": PRODUCT,
				"reference_name": product.name,
				"reference_field": "display_name",
				"language": "ar",
				"translated_value": "قميص",
			}
		).insert()
		self.assertEqual(self.titles([product], self.arabic)[0].status, CURRENT)

		frappe.db.set_value(PRODUCT, product.name, "display_name", f"{product.display_name} v2")
		product.reload()
		self.assertEqual(self.titles([product], self.arabic)[0].status, OUTDATED)

		translation.translated_value = "قميص جديد"
		translation.save()
		self.assertEqual(self.titles([product], self.arabic)[0].status, CURRENT)

	def test_registering_a_field_another_request_just_translated_updates_that_row(self):
		product = self.make_product("RACE")
		first = register(PRODUCT, product.name, "display_name", "ar", "قميص")
		original_get_value = frappe.db.get_value
		lookups = []

		def miss_the_first_lookup(doctype, *args, **kwargs):
			# The other request inserted its row after this one looked.
			if doctype == "Content Translation" and not lookups:
				lookups.append(doctype)
				return None
			return original_get_value(doctype, *args, **kwargs)

		with patch.object(frappe.db, "get_value", miss_the_first_lookup):
			second = register(PRODUCT, product.name, "display_name", "ar", "قميص الكتان")

		self.assertEqual(second, first)
		self.assertEqual(frappe.db.get_value("Content Translation", first, "translated_value"), "قميص الكتان")

	def test_content_translations_stay_out_of_frappes_translation_dictionary(self):
		product = self.make_product("DICT")
		register(PRODUCT, product.name, "display_name", "ar", "قميص الكتان")
		frappe.translate.clear_cache()

		self.assertNotIn(product.display_name, get_all_translations("ar"))
		self.assertNotIn("قميص الكتان", get_all_translations("ar").values())
		self.assertEqual(frappe._(product.display_name, lang="ar"), product.display_name)

	def test_only_declared_fields_can_be_translated(self):
		product = self.make_product("UNDECLARED")

		self.assertIn("display_name", get_translatable_fields(PRODUCT))
		with self.assertRaisesRegex(frappe.ValidationError, "is not a translatable field"):
			register(PRODUCT, product.name, "route", "ar", "قميص")

	def test_another_app_registers_its_own_resource_through_the_hook(self):
		note = frappe.get_doc({"doctype": "Note", "title": f"Packing note {self.suffix}"}).insert()
		resource = {"type": "note", "doctype": "Note", "fields": ["title"], "label": "Notes"}
		commera_hooks = frappe.get_hooks("commera_hooks", {})
		hooks = {
			**commera_hooks,
			"translatable_resources": [*commera_hooks["translatable_resources"], resource],
		}

		with self.patch_hooks({"commera_hooks": hooks}):
			register("Note", note.name, "title", "ar", "ملاحظة التغليف")
			title = translate([note], ["title"], self.arabic)[0]["title"]
			resources = {resource.type: resource for resource in get_translatable_resources()}

		self.assertEqual((title.value, title.status), ("ملاحظة التغليف", CURRENT))
		self.assertEqual(resources["note"].fields, ("title",))
		self.assertEqual(resources["product"].doctype, PRODUCT)

	def test_deleting_a_record_deletes_its_translations(self):
		product = self.make_product("DELETE")
		register(PRODUCT, product.name, "display_name", "ar", "قميص الكتان")

		frappe.delete_doc(PRODUCT, product.name)

		self.assertFalse(frappe.db.exists("Content Translation", {"reference_name": product.name}))


class TestTranslatedProductTitles(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		set_storefront_languages("en", published=("en", "ar"))

	def test_the_product_card_and_the_product_page_show_the_same_translated_title(self):
		route = self.make_priced_variant("TITLE", default_rate=30)
		product = frappe.get_doc(PRODUCT, {"route": route})
		register(PRODUCT, product.name, "display_name", "ar", "قميص الكتان")

		use_storefront_language(self, "ar")
		self.assertEqual(catalog.get_product_cards_for([product.name])[0]["title"], "قميص الكتان")
		self.assertEqual(catalog.get_product(route)["title"], "قميص الكتان")

		use_storefront_language(self, "en")
		self.assertEqual(catalog.get_product_cards_for([product.name])[0]["title"], product.display_name)
		self.assertEqual(catalog.get_product(route)["title"], product.display_name)
