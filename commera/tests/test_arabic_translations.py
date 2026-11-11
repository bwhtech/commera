from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.translate import get_boot_translations
from frappe.utils.jinja import get_jenv

from commera.api.storefront.translations import get_translations
from commera.localization.untranslated import (
	Message,
	check_translations,
	extract_client_t_messages,
	extract_messages,
	get_messages,
	markup_matches,
)
from commera.shop_themes.theme_resolver import get_theme_environment
from commera.tests.test_localization import use_storefront_languages

STARTER_THEME = Path(__file__).resolve().parents[1] / "themes" / "commera_starter"
FIX_HINT = (
	"Add each string to commera/translations/ar.csv. Run `bench commera check-translations` to list them."
)


class TestArabicCatalog(IntegrationTestCase):
	def test_every_ui_string_has_an_arabic_translation(self):
		problems = [str(problem) for problem in check_translations("ar")]
		self.assertEqual(problems, [], FIX_HINT)

	def test_the_check_covers_every_source(self):
		paths = {"/".join(Path(message.path).parts[:2]) for message in get_messages()}
		self.assertTrue(
			{"commera/themes", "commera/sdk", "packages/storefront", "dashboard/src"} <= paths, paths
		)

	def test_the_check_reads_t_calls_and_translation_contexts(self):
		path = self.write_source(
			"sample.vue",
			"<p x-text=\"commera.t('Please Select')\"></p>\n"
			"{{ __('Updated', null, 'Date last updated') }}\n"
			"<b>{{ format(count) }} {{ t(`Hello`) }}</b>",
		)
		found = {(message.text, message.context, message.line) for message in extract_messages(path)}
		self.assertEqual(
			found, {("Please Select", None, 1), ("Updated", "Date last updated", 2), ("Hello", None, 3)}
		)

	def test_a_missing_or_broken_translation_fails_the_check(self):
		messages = [
			Message("Hello {0}", None, "dashboard/src/a.vue", 1),
			Message("<b>Bold</b>", None, "dashboard/src/a.vue", 2),
			Message("New", None, "dashboard/src/a.vue", 3),
		]
		translations = {"Hello {0}": "مرحبًا", "<b>Bold</b>": "<b>عريض</b>"}
		with (
			patch("commera.localization.untranslated.get_messages", return_value=messages),
			patch("commera.localization.untranslated.get_app_translations", return_value=translations),
		):
			problems = [(problem.message.text, problem.reason) for problem in check_translations("ar")]

		self.assertEqual(problems, [("Hello {0}", "placeholders or tags differ"), ("New", "untranslated")])

	def test_dynamic_translation_arguments_are_rejected(self):
		for code in [
			"t(message)",
			"t (message)",
			"t?.(message)",
			"commera.t?.(message)",
			"t((message))",
			't(("Hello") + name)',
			"t('Hello' + name)",
			"t(`Hello ${name}`)",
			"commera.t(prefix + 'Hello')",
		]:
			with self.subTest(code=code), self.assertRaisesRegex(ValueError, "line 1"):
				extract_client_t_messages(code)

	def test_static_javascript_arguments(self):
		for code, expected in [
			('t(("Hello"))', "Hello"),
			('t("Hello /* world */")', "Hello /* world */"),
			('t?.("Hello")', "Hello"),
			("commera . t?.((`Hello`))", "Hello"),
			("t(/* comment */ 'Hello', values)", "Hello"),
			(r't("Hello\nworld")', "Hello\nworld"),
		]:
			with self.subTest(code=code):
				self.assertEqual(extract_client_t_messages(code), [(1, expected, None)])

	def test_javascript_non_calls_are_ignored(self):
		for code in [
			'const text = "t(message)";',
			"const x = 1; // t(message)",
			"/* t(message) */",
			"const text = `t(message)`;",
			r"const expression = /t(message)/;",
			"other . t(message)",
			"other.commera.t(message)",
			"function t(message) {}",
		]:
			with self.subTest(code=code):
				self.assertEqual(extract_client_t_messages(code), [])

	def test_dynamic_optional_calls_report_file_and_line(self):
		path = self.write_source("dynamic.js", "\nconst value = t?.(message)")
		with self.assertRaisesRegex(ValueError, r"dynamic.js: line 2"):
			extract_messages(path)

	def test_markup_requires_nested_tags_and_complete_format_fields(self):
		self.assertFalse(markup_matches("<b><i>Hello</i></b>", "<b><i>مرحبا</b></i>"))
		self.assertFalse(markup_matches("{0:.2f}", "{0}"))
		self.assertFalse(markup_matches("{value!r:>{width}}", "{value!s:>{width}}"))
		self.assertTrue(markup_matches("<b>{0:.2f}</b><br>", "<b>{0:.2f}</b><br>"))

	def write_source(self, name, code):
		path = Path(frappe.get_site_path("private", "files", name))
		path.write_text(code, encoding="utf-8")
		self.addCleanup(path.unlink)
		return path


class TestArabicSurfaces(IntegrationTestCase):
	def setUp(self):
		# The site cache may hold a dictionary built from another checkout's translation files.
		frappe.translate.clear_cache()
		self.addCleanup(frappe.translate.clear_cache)
		self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
		frappe.local.lang = "ar"

	def test_the_starter_search_and_cart_render_in_arabic(self):
		environment = get_theme_environment(get_jenv(), [str(STARTER_THEME)])
		search = environment.get_template("theme://components/search_modal.html").render({})
		cart = environment.get_template("theme://components/cart_contents.html").render({})

		self.assertIn("ابحث باسم المنتج أو اللون أو العلامة التجارية.", search)
		self.assertIn("سلتك فارغة", cart)
		self.assertNotIn("Your cart is empty", cart)

	def test_sdk_errors_are_in_arabic(self):
		self.assertEqual(frappe._("Add something to your cart first."), "أضف شيئًا إلى سلتك أولًا.")

	def test_the_storefront_dictionary_translates_the_package_strings(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		dictionary = get_translations("ar")

		self.assertEqual(dictionary["Could not reach the store."], "تعذّر الوصول إلى المتجر.")
		self.assertEqual(dictionary["Not found."], "غير موجود.")

	def test_the_dashboard_dictionary_is_in_arabic(self):
		dictionary = get_boot_translations("ar")

		self.assertEqual(dictionary["Switch language"], "تغيير اللغة")
		self.assertEqual(dictionary["Submitted:Date a review was submitted"], "تاريخ الإرسال")
