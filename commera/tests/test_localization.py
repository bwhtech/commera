import json
import re

import frappe
from frappe.tests import IntegrationTestCase
from frappe.website.path_resolver import PathResolver
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.localization import get_localization, resolve
from commera.shop_themes.theme_resolver import build_base_context

STOREFRONT_CONFIG_PATTERN = re.compile(r"window\.commera_storefront_config = (.*);")


def set_storefront_languages(default=None, published=(), unpublished=()):
	"""Write the language settings straight to the database: saving Commera Settings runs unrelated checks."""
	frappe.db.delete("Commera Storefront Language", {"parent": "Commera Settings"})
	rows = [(code, 1) for code in published] + [(code, 0) for code in unpublished]
	for idx, (code, is_published) in enumerate(rows, start=1):
		frappe.get_doc(
			{
				"doctype": "Commera Storefront Language",
				"parent": "Commera Settings",
				"parenttype": "Commera Settings",
				"parentfield": "storefront_languages",
				"idx": idx,
				"language": code,
				"published": is_published,
			}
		).db_insert()
	frappe.db.set_single_value("Commera Settings", "default_storefront_language", default or "")
	frappe.clear_document_cache("Commera Settings", "Commera Settings")
	frappe.local.request_cache.clear()


def use_storefront_languages(test, default=None, published=(), unpublished=()):
	"""set_storefront_languages for one test. The cached settings would outlive the rollback."""
	set_storefront_languages(default, published, unpublished)
	test.addCleanup(frappe.local.request_cache.clear)
	test.addCleanup(frappe.clear_document_cache, "Commera Settings", "Commera Settings")


def codes(languages):
	return [language.code for language in languages]


class TestLocalizationResolver(IntegrationTestCase):
	def setUp(self):
		set_storefront_languages("en", published=("en", "ar"), unpublished=("fr",))

	def test_a_language_prefix_sets_the_language_and_is_removed_from_the_path(self):
		localization, path = resolve("/ar/products/linen-shirt")

		self.assertEqual(localization.language.code, "ar")
		self.assertEqual(localization.root_prefix, "/ar")
		self.assertEqual(path, "/products/linen-shirt")
		self.assertEqual(resolve("/AR/cart")[0].root_prefix, "/ar")
		self.assertEqual(resolve("/ar")[1], "/")
		self.assertEqual(resolve("/en/cart")[0].language.code, "en")

	def test_a_prefix_matches_only_a_whole_path_segment(self):
		for path in ("/archive", "/article/one", "/arabic", "/english", "/"):
			with self.subTest(path):
				localization, rest = resolve(path)
				self.assertEqual(localization.language.code, "en")
				self.assertEqual(localization.root_prefix, "")
				self.assertEqual(rest, path)

	def test_a_language_code_matches_in_any_case(self):
		self.assertEqual(resolve("/AR/cart")[0].language.code, "ar")

	def test_an_unpublished_language_resolves_only_for_admins(self):
		as_guest, guest_path = resolve("/fr/products", include_unpublished=False)
		self.assertEqual(as_guest.language.code, "en")
		self.assertEqual(guest_path, "/fr/products")

		as_admin, admin_path = resolve("/fr/products", include_unpublished=True)
		self.assertEqual(as_admin.language.code, "fr")
		self.assertEqual(admin_path, "/products")

	def test_lang_parameter_picks_a_language_when_the_path_has_no_prefix(self):
		self.assertEqual(resolve("/api/method/commera.api.cart", "ar")[0].language.code, "ar")
		self.assertEqual(resolve("/api/method/commera.api.cart", "ar")[0].root_prefix, "/ar")
		self.assertEqual(resolve("/api/method/commera.api.cart", "de")[0].language.code, "en")
		self.assertEqual(resolve("/api/method/commera.api.cart", "fr")[0].language.code, "en")
		self.assertEqual(resolve("/ar/cart", "en")[0].language.code, "ar")

	def test_available_languages_are_the_published_ones_with_the_default_first(self):
		set_storefront_languages("ar", published=("en", "ar"), unpublished=("fr",))

		localization, _path = resolve("/", include_unpublished=True)

		self.assertEqual(codes(localization.available_languages), ["ar", "en"])
		self.assertEqual(localization.default_language.code, "ar")

	def test_the_default_language_falls_back_to_system_settings_then_english(self):
		set_storefront_languages()
		system_language = frappe.get_system_settings("language") or "en"

		self.assertEqual(resolve("/")[0].default_language.code, system_language)
		self.assertEqual(codes(resolve("/")[0].available_languages), [system_language])

	def test_localization_describes_each_language(self):
		localization = resolve("/ar/")[0].as_dict()

		self.assertEqual(
			localization["language"],
			{"code": "ar", "name": "Arabic", "endonym": "العربية", "direction": "rtl"},
		)
		self.assertEqual(localization["default_language"]["direction"], "ltr")
		self.assertEqual([language["code"] for language in localization["available_languages"]], ["en", "ar"])
		self.assertEqual(localization["root_prefix"], "/ar")

	def test_direction_follows_frappes_right_to_left_set(self):
		set_storefront_languages("en", published=("en", "he", "fa", "de"))

		directions = {language.code: language.direction for language in resolve("/")[0].available_languages}

		self.assertEqual(directions, {"en": "ltr", "he": "rtl", "fa": "rtl", "de": "ltr"})


class TestRequestLanguage(IntegrationTestCase):
	def setUp(self):
		set_storefront_languages("en", published=("en", "ar"))
		self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
		self.addCleanup(frappe.local.request_cache.clear)

	def visit(self, path, lang="ar"):
		frappe.local.request = Request(EnvironBuilder(path=path).get_environ())
		frappe.local.request_cache.clear()
		frappe.local.lang = lang
		PathResolver(path).resolve()
		return frappe.local.lang

	def test_a_language_prefix_sets_frappes_language(self):
		self.assertEqual(self.visit("/ar/products", lang="en"), "ar")
		self.assertEqual(self.visit("/products"), "en")

	def test_other_paths_keep_frappes_language(self):
		for path in ("/archive", "/article", "/app/item", "/commera/orders", "/builder"):
			with self.subTest(path):
				self.assertEqual(self.visit(path, lang="en"), "en")
				self.assertEqual(self.visit(path, lang="fr"), "fr")

	def test_storefront_config_and_theme_context_carry_the_localization(self):
		self.visit("/ar/products")

		context = build_base_context(None)
		config = json.loads(STOREFRONT_CONFIG_PATTERN.search(context.commera_header_content).group(1))

		self.assertEqual(context.localization, get_localization())
		self.assertEqual(config["language"], "ar")
		self.assertEqual(config["localization"]["language"]["code"], "ar")
		self.assertEqual(config["localization"]["default_language"]["code"], "en")
		self.assertEqual(config["localization"]["root_prefix"], "/ar")


class TestStorefrontLanguageSettings(IntegrationTestCase):
	def settings_with(self, default, rows):
		settings = frappe.get_doc({"doctype": "Commera Settings", "default_storefront_language": default})
		for code, published in rows:
			settings.append("storefront_languages", {"language": code, "published": published})
		return settings

	def test_a_storefront_has_at_most_twenty_languages(self):
		languages = frappe.get_all("Language", pluck="name", limit=21, order_by="name")
		self.assertEqual(len(languages), 21)

		with self.assertRaises(frappe.ValidationError):
			self.settings_with(
				languages[0], [(code, 1) for code in languages]
			).validate_storefront_languages()
		self.settings_with(
			languages[0], [(code, 1) for code in languages[:20]]
		).validate_storefront_languages()

	def test_a_language_is_listed_once(self):
		with self.assertRaises(frappe.ValidationError):
			self.settings_with("en", [("ar", 1), ("ar", 0)]).validate_storefront_languages()

	def test_the_default_language_row_is_always_published(self):
		settings = self.settings_with("ar", [("en", 1), ("ar", 0)])

		settings.validate_storefront_languages()

		self.assertEqual(settings.storefront_languages[1].published, 1)


class TestSeedStorefrontLanguagesPatch(IntegrationTestCase):
	def test_an_existing_store_keeps_english_and_arabic_published(self):
		from commera.patches import seed_storefront_languages

		set_storefront_languages()

		seed_storefront_languages.execute()
		frappe.local.request_cache.clear()

		localization, _path = resolve("/")
		self.assertEqual(localization.default_language.code, "en")
		self.assertEqual(codes(localization.available_languages), ["en", "ar"])

	def test_a_store_with_languages_is_left_alone(self):
		from commera.patches import seed_storefront_languages

		set_storefront_languages("en", published=("en", "fr"))

		seed_storefront_languages.execute()
		frappe.local.request_cache.clear()

		self.assertEqual(codes(resolve("/")[0].available_languages), ["en", "fr"])

	def test_a_new_store_starts_with_only_its_default_language(self):
		from commera.migrate import seed_default_storefront_language

		set_storefront_languages()

		seed_default_storefront_language()
		frappe.local.request_cache.clear()

		system_language = frappe.get_system_settings("language") or "en"
		self.assertEqual(codes(resolve("/")[0].available_languages), [system_language])
		self.assertEqual(
			frappe.db.get_single_value("Commera Settings", "default_storefront_language"), system_language
		)
