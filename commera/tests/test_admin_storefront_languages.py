from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin import storefront_languages as api
from commera.localization.languages import MAX_STOREFRONT_LANGUAGES
from commera.tests.test_localization import use_storefront_languages

SETTINGS_REBUILD = "commera.commera_ecommerce.doctype.commera_settings.commera_settings.enqueue_full_rebuild"


def rows(screen):
	return [(language["code"], language["published"]) for language in screen["languages"]]


class TestAdminStorefrontLanguages(IntegrationTestCase):
	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar"), unpublished=("fr",))
		# A settings save also checks that checkout has a payment method.
		frappe.db.set_single_value("Commera Settings", "cod_enabled", 1)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")
		rebuild = patch(SETTINGS_REBUILD)
		rebuild.start()
		self.addCleanup(rebuild.stop)

	def test_the_screen_lists_the_rows_in_order_with_their_names_and_direction(self):
		screen = api.get_storefront_languages()

		self.assertEqual(screen["default_language"], "en")
		self.assertEqual(screen["max_languages"], MAX_STOREFRONT_LANGUAGES)
		self.assertEqual(rows(screen), [("en", True), ("ar", True), ("fr", False)])
		arabic = screen["languages"][1]
		self.assertEqual(arabic["name"], "Arabic")
		self.assertEqual(arabic["endonym"], "العربية")
		self.assertEqual(arabic["direction"], "rtl")

	def test_a_default_without_a_row_is_listed_first_and_gets_a_row_on_the_next_write(self):
		use_storefront_languages(self, "en", published=("ar",))

		self.assertEqual(rows(api.get_storefront_languages()), [("en", True), ("ar", True)])

		screen = api.set_storefront_language_published("ar", 0)
		self.assertEqual(rows(screen), [("en", True), ("ar", False)])

	def test_adding_a_language_appends_it_published_or_hidden(self):
		screen = api.add_storefront_language("de")
		self.assertEqual(rows(screen)[-1], ("de", False))

		screen = api.add_storefront_language("es", published=1)
		self.assertEqual(rows(screen)[-1], ("es", True))

	def test_adding_a_listed_or_disabled_language_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "already a storefront language"):
			api.add_storefront_language("ar")

		with self.assertRaisesRegex(frappe.ValidationError, "not an enabled language"):
			api.add_storefront_language("not-a-language")

	def test_the_twenty_first_language_is_refused_with_the_settings_message(self):
		# Any Language fills a row; only the one being added must be enabled.
		codes = frappe.get_all(
			"Language",
			filters={"name": ("not in", ("en", "ar", "fr", "de"))},
			pluck="name",
			order_by="name",
			limit=MAX_STOREFRONT_LANGUAGES - 3,
		)
		use_storefront_languages(self, "en", published=("en", "ar"), unpublished=("fr", *codes))
		frappe.db.set_value("Language", "de", "enabled", 1)

		with self.assertRaisesRegex(frappe.ValidationError, "at most 20 languages"):
			api.add_storefront_language("de")

	def test_publishing_and_hiding_a_language(self):
		self.assertEqual(rows(api.set_storefront_language_published("fr", 1))[-1], ("fr", True))
		self.assertEqual(rows(api.set_storefront_language_published("ar", 0))[1], ("ar", False))

	def test_the_default_language_cannot_be_hidden_or_removed(self):
		with self.assertRaisesRegex(frappe.ValidationError, "always see the default"):
			api.set_storefront_language_published("en", 0)

		with self.assertRaisesRegex(frappe.ValidationError, "before you remove English"):
			api.remove_storefront_language("en")

	def test_removing_a_language_keeps_the_order_of_the_rest(self):
		screen = api.remove_storefront_language("ar")

		self.assertEqual(rows(screen), [("en", True), ("fr", False)])
		self.assertFalse(frappe.db.exists("Commera Storefront Language", {"language": "ar"}))

	def test_moving_a_language_changes_the_stored_order(self):
		self.assertEqual(
			[code for code, _ in rows(api.move_storefront_language("fr", -1))], ["en", "fr", "ar"]
		)
		self.assertEqual(
			[code for code, _ in rows(api.move_storefront_language("en", 1))], ["fr", "en", "ar"]
		)
		# A move past either end stops there.
		self.assertEqual(
			[code for code, _ in rows(api.move_storefront_language("ar", 5))], ["fr", "en", "ar"]
		)

		stored = frappe.get_all(
			"Commera Storefront Language",
			filters={"parent": "Commera Settings"},
			pluck="language",
			order_by="idx",
		)
		self.assertEqual(stored, ["fr", "en", "ar"])

	def test_making_a_published_language_the_default(self):
		screen = api.set_default_storefront_language("ar")

		self.assertEqual(screen["default_language"], "ar")
		self.assertEqual(frappe.db.get_single_value("Commera Settings", "default_storefront_language"), "ar")
		self.assertEqual(rows(screen), [("en", True), ("ar", True), ("fr", False)])

	def test_a_hidden_language_cannot_become_the_default(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Publish French before"):
			api.set_default_storefront_language("fr")

	def test_a_user_without_settings_access_is_refused(self):
		with self.set_user("Guest"):
			with self.assertRaises(frappe.PermissionError):
				api.get_storefront_languages()
			with self.assertRaises(frappe.PermissionError):
				api.add_storefront_language("de")


class TestLanguageSettingsRoles(IntegrationTestCase):
	setUp = TestAdminStorefrontLanguages.setUp

	def make_user(self, role=None):
		return (
			frappe.get_doc(
				{
					"doctype": "User",
					"email": f"language-settings-{frappe.generate_hash(length=10)}@example.com",
					"first_name": "Language settings test",
					"user_type": "System User" if role else "Website User",
					"send_welcome_email": 0,
					"roles": [{"role": role}] if role else [],
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def test_commera_admin_can_read_and_perform_every_language_action(self):
		with self.set_user(self.make_user("Commera Admin")):
			self.assertNotIn("System Manager", frappe.get_roles())
			self.assertEqual(api.get_storefront_languages()["default_language"], "en")
			self.assertEqual(rows(api.add_storefront_language("de"))[-1], ("de", False))
			self.assertEqual(rows(api.set_storefront_language_published("de", 1))[-1], ("de", True))
			self.assertEqual(rows(api.move_storefront_language("de", -1))[2], ("de", True))
			self.assertEqual(api.set_default_storefront_language("de")["default_language"], "de")
			self.assertNotIn("fr", [code for code, _ in rows(api.remove_storefront_language("fr"))])

	def test_authenticated_website_customer_cannot_read_or_write_languages(self):
		with self.set_user(self.make_user()):
			for action, arguments in (
				(api.get_storefront_languages, ()),
				(api.add_storefront_language, ("de",)),
				(api.remove_storefront_language, ("fr",)),
				(api.set_storefront_language_published, ("fr", 1)),
				(api.move_storefront_language, ("fr", -1)),
				(api.set_default_storefront_language, ("ar",)),
			):
				with self.subTest(action=action.__name__), self.assertRaises(frappe.PermissionError):
					action(*arguments)
