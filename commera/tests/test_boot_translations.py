import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_build_version

from commera.localization.boot_translations import get_boot_translations, get_translation_version


class TestBootTranslations(IntegrationTestCase):
	def make_translation(self):
		return frappe.get_doc(
			{
				"doctype": "Translation",
				"language": "ar",
				"source_text": "Boot translations test string",
				"translated_text": "نص اختبار الترجمة",
			}
		).insert()

	def test_the_version_holds_until_translations_change(self):
		version = get_translation_version()

		self.assertEqual(get_translation_version(), version)
		self.assertTrue(version.endswith(f"_{get_build_version()}"))

	def test_saving_a_translation_changes_the_version(self):
		version = get_translation_version()
		self.make_translation()

		self.assertNotEqual(get_translation_version(), version)

	def test_deleting_a_translation_changes_the_version(self):
		translation = self.make_translation()
		version = get_translation_version()
		translation.delete()

		self.assertNotEqual(get_translation_version(), version)

	def test_the_dictionary_is_in_the_asked_language(self):
		self.make_translation()

		self.assertEqual(get_boot_translations("ar")["Boot translations test string"], "نص اختبار الترجمة")

	def test_an_unknown_language_falls_back_to_the_request_language(self):
		self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
		frappe.local.lang = "ar"
		self.make_translation()

		self.assertIn("Boot translations test string", get_boot_translations("not-a-language"))
