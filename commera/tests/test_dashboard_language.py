from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.translate import get_translation_version

from commera.api.admin import language as dashboard_language
from commera.www import commera as dashboard


class TestDashboardLanguage(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(self.set_admin_language, frappe.db.get_value("User", "Administrator", "language"))
		self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)

	def set_admin_language(self, language):
		frappe.db.set_value("User", "Administrator", "language", language)

	def get_boot(self) -> frappe._dict:
		with self.set_user("Administrator"), patch.object(frappe.db, "commit"):
			return dashboard.get_boot()

	def test_the_admins_own_language_wins(self):
		self.set_admin_language("de")

		with patch.object(frappe, "get_system_settings", return_value="fr"):
			self.assertEqual(dashboard_language.get_dashboard_language("Administrator"), "de")

	def test_an_admin_without_a_language_gets_the_sites(self):
		self.set_admin_language(None)

		with patch.object(frappe, "get_system_settings", return_value="fr"):
			self.assertEqual(dashboard_language.get_dashboard_language("Administrator"), "fr")

		with patch.object(frappe, "get_system_settings", return_value=None):
			self.assertEqual(dashboard_language.get_dashboard_language("Administrator"), "en")

	def test_boot_carries_the_admins_language_and_the_translations_version(self):
		self.set_admin_language("ar")
		frappe.local.lang = "en"

		boot = self.get_boot()

		self.assertEqual(boot.lang, "ar")
		self.assertTrue(boot.is_rtl)
		self.assertEqual(boot.translations_version, get_translation_version())
		self.assertNotIn("translations", boot)

	def test_a_left_to_right_language_does_not_mirror(self):
		self.set_admin_language("de")

		self.assertFalse(self.get_boot().is_rtl)

	def test_set_language_changes_the_admins_language(self):
		with self.set_user("Administrator"):
			dashboard_language.set_language("ar")

		self.assertEqual(frappe.db.get_value("User", "Administrator", "language"), "ar")
		self.assertEqual(dashboard_language.get_dashboard_language("Administrator"), "ar")

	def test_set_language_applies_the_languages_formats_and_clears_the_boot_cache(self):
		self.set_admin_language("en")
		formats = {
			"date_format": "dd/mm/yyyy",
			"number_format": "#.###,##",
			"first_day_of_the_week": "Saturday",
		}
		before = frappe.db.get_value("Language", "ar", list(formats), as_dict=True)
		# set_value adds the modified fields to the dict it gets.
		frappe.db.set_value("Language", "ar", dict(formats))
		self.addCleanup(frappe.db.set_value, "Language", "ar", before)
		for key in formats:
			self.addCleanup(frappe.defaults.clear_default, key, parent="Administrator")
		frappe.cache.hset("bootinfo", "Administrator", {"lang": "en"})

		with self.set_user("Administrator"):
			dashboard_language.set_language("ar")

		for key, value in formats.items():
			self.assertEqual(frappe.defaults.get_user_default(key, "Administrator"), value)
		self.assertIsNone(frappe.cache.hget("bootinfo", "Administrator"))

	def test_set_language_refuses_a_disabled_language(self):
		frappe.db.set_value("Language", "de", "enabled", 0)
		self.addCleanup(frappe.db.set_value, "Language", "de", "enabled", 1)

		with self.set_user("Administrator"), self.assertRaises(frappe.ValidationError):
			dashboard_language.set_language("de")

	def test_languages_are_named_in_their_own_script(self):
		self.set_admin_language("ar")

		with self.set_user("Administrator"):
			payload = dashboard_language.get_languages()

		languages = {language["code"]: language for language in payload["languages"]}
		self.assertEqual(payload["current"], "ar")
		self.assertEqual(languages["ar"]["endonym"], "العربية")
		self.assertEqual(languages["ar"]["name"], "Arabic")

	def test_a_website_user_cannot_change_the_dashboard_language(self):
		with self.set_user("Guest"), self.assertRaises(frappe.PermissionError):
			dashboard_language.set_language("ar")
