import json

import frappe

from commera.api.storefront.translations import get_translations
from commera.localization import register, resolve
from commera.shop_themes.storefront_header import render_storefront_header
from commera.tests.test_content_translation import PRODUCT
from commera.tests.test_localization import STOREFRONT_CONFIG_PATTERN, use_storefront_languages
from commera.tests.test_product_details import ProductDetailPriceTestCase

# A UI string with an Arabic translation in commera/translations/ar.csv.
UI_STRING = "Only {0} left"


class TestStorefrontTranslations(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		use_storefront_languages(self, "en", published=("en", "ar"), unpublished=("fr",))

	def as_guest(self):
		self.addCleanup(frappe.set_user, frappe.session.user)
		frappe.set_user("Guest")  # nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser

	def add_ui_translation(self, language, source, translated):
		translation = frappe.get_doc(
			{
				"doctype": "Translation",
				"language": language,
				"source_text": source,
				"translated_text": translated,
			}
		).insert()
		self.addCleanup(frappe.delete_doc, "Translation", translation.name, force=True)

	def get_page_config(self, path):
		header = render_storefront_header(resolve(path)[0])
		return json.loads(STOREFRONT_CONFIG_PATTERN.search(header).group(1))

	def test_a_guest_gets_the_ui_strings_of_a_published_language(self):
		self.as_guest()
		self.assertEqual(get_translations("ar")[UI_STRING], "تبقّى {0} فقط")

	def test_a_merchant_translation_overrides_the_shipped_one(self):
		self.add_ui_translation("ar", UI_STRING, "باقي {0} قطع")
		self.as_guest()
		self.assertEqual(get_translations("ar")[UI_STRING], "باقي {0} قطع")

	def test_the_dictionary_is_built_in_its_own_language_not_the_request_language(self):
		frappe.translate.clear_cache()
		self.addCleanup(frappe.translate.clear_cache)
		self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
		frappe.local.lang = "fr"

		self.as_guest()
		self.assertEqual(get_translations("ar")["Germany"], "ألمانيا")

	def test_record_content_stays_out_of_the_dictionary(self):
		route = self.make_priced_variant("Dictionary Linen Shirt", default_rate=30)
		product = frappe.get_doc(PRODUCT, {"route": route})
		register(PRODUCT, product.name, "display_name", "ar", "قميص كتان القاموس")

		self.as_guest()
		dictionary = get_translations("ar")
		self.assertNotIn(product.display_name, dictionary)
		self.assertNotIn("قميص كتان القاموس", dictionary.values())

	def test_an_unpublished_or_unknown_language_is_refused_to_guests(self):
		self.as_guest()
		for code in ("fr", "de"):
			with self.subTest(code), self.assertRaises(frappe.DoesNotExistError):
				get_translations(code)

	def test_an_admin_previews_an_unpublished_language(self):
		self.assertIsInstance(get_translations("fr"), dict)

	def test_an_english_page_without_overrides_needs_no_dictionary(self):
		use_storefront_languages(self, "en", published=("en",))
		self.assertIsNone(self.get_page_config("/")["translations_version"])

	def test_an_english_override_or_another_language_needs_a_dictionary(self):
		self.assertTrue(self.get_page_config("/ar")["translations_version"])

		self.add_ui_translation("en", "Add to cart", "Add to bag")
		self.assertTrue(self.get_page_config("/")["translations_version"])
