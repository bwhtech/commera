# Copyright (c) 2026, ivend and Contributors
# Merchant-authored content pages: routing, language fallback, translations and the guest 404.

import frappe
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.localization import get_translatable_fields, register
from commera.patches.seed_shop_web_page_route import execute as seed_shop_web_page_route
from commera.sdk import shop
from commera.tests.test_content_translation import use_storefront_language
from commera.tests.test_localization import use_storefront_languages
from commera.www.shop_web_page import index as www_shop_web_page

PAGE = "Shop Web Page"

ENGLISH_CONTENT = "<p>Free returns within 30 days.</p>"
ARABIC_CONTENT = "<p>إرجاع مجاني خلال 30 يومًا.</p>"


class ShopWebPageTestCase(IntegrationTestCase):
	def setUp(self):
		self.tag = frappe.generate_hash(length=8)
		self.saved_request = getattr(frappe.local, "request", None)
		self.saved_lang = frappe.local.lang
		self.addCleanup(self.restore_locals)
		self.addCleanup(frappe.set_user, frappe.session.user)
		use_storefront_languages(self, "en", published=("en", "ar"))

	def restore_locals(self):
		frappe.local.request = self.saved_request
		frappe.local.lang = self.saved_lang

	def make_page(self, title=None, **fields):
		page = frappe.new_doc("Shop Web Page")
		page.name = title or f"Returns Policy {self.tag}"
		page.content = ENGLISH_CONTENT
		page.update(fields)
		return page.insert()

	def run_context(self, route, lang="en", frappe_lang=None):
		"""The www page context on /<lang>/page/<route>. `frappe_lang` sets frappe.local.lang apart."""
		frappe.local.lang = frappe_lang or lang
		frappe.local.request = Request(EnvironBuilder(path=f"/{lang}/page/{route}").get_environ())
		frappe.form_dict.route = route
		self.addCleanup(frappe.form_dict.pop, "route", None)

		context = frappe._dict()
		www_shop_web_page.get_context(context)
		return context


class TestShopWebPage(ShopWebPageTestCase):
	def test_a_blank_route_is_scrubbed_off_the_title(self):
		page = self.make_page(title=f"Shipping & Returns_Policy {self.tag}")
		self.assertEqual(page.route, f"shipping-returns-policy-{self.tag.lower()}")

	def test_a_second_page_cannot_claim_a_taken_route(self):
		taken_route = self.make_page().route
		self.assertRaises(
			frappe.ValidationError, self.make_page, title=f"Other {self.tag}", route=taken_route
		)

	def test_english_content_renders_on_the_english_route(self):
		page = self.make_page()
		context = self.run_context(page.route)
		self.assertEqual(context.content, ENGLISH_CONTENT)
		self.assertEqual(context.breadcrumbs, [{"label": page.name, "href": f"/en/page/{page.route}"}])
		self.assertIn(page.name, context.seo["title"])
		self.assertFalse(context.seo["noindex"])

	def test_arabic_content_renders_on_the_arabic_route(self):
		page = self.make_page()
		register(PAGE, page.name, "content", "ar", ARABIC_CONTENT)
		self.assertEqual(self.run_context(page.route, lang="ar").content, ARABIC_CONTENT)

	def test_arabic_falls_back_to_english_when_untranslated(self):
		page = self.make_page()
		self.assertEqual(self.run_context(page.route, lang="ar").content, ENGLISH_CONTENT)

	def test_an_unpublished_page_is_a_404_for_a_shopper(self):
		page = self.make_page(published=0)
		frappe.set_user("Guest")
		self.assertRaises(frappe.DoesNotExistError, self.run_context, page.route)

	def test_a_shopper_cannot_read_a_draft_through_the_permission_layer(self):
		"""No role holds `read`, so frappe.client and the admin API cannot hand a draft to a shopper."""
		draft = self.make_page(published=0)
		frappe.set_user("Guest")

		self.assertFalse(frappe.has_permission("Shop Web Page", "read"))
		self.assertRaises(
			frappe.PermissionError, frappe.get_doc("Shop Web Page", draft.name).check_permission, "read"
		)

	def test_a_published_page_renders_for_a_guest(self):
		page = self.make_page()
		frappe.set_user("Guest")
		self.assertEqual(self.run_context(page.route).content, ENGLISH_CONTENT)

	def test_an_unpublished_page_still_previews_for_its_editor(self):
		page = self.make_page(published=0)
		self.assertEqual(self.run_context(page.route).content, ENGLISH_CONTENT)

	def test_an_unknown_route_is_a_404(self):
		self.assertRaises(frappe.DoesNotExistError, self.run_context, f"no-such-page-{self.tag}")


class TestShopWebPageTranslation(ShopWebPageTestCase):
	def setUp(self):
		super().setUp()
		self.page = self.make_page(meta_title="Returns", meta_description="Our returns policy")
		self.translate_page(self.page, "سياسة الإرجاع", ARABIC_CONTENT)
		register(PAGE, self.page.name, "meta_title", "ar", "الإرجاع")
		register(PAGE, self.page.name, "meta_description", "ar", "سياسة الإرجاع لدينا")

	def translate_page(self, page, title, content):
		register(PAGE, page.name, "title", "ar", title)
		register(PAGE, page.name, "content", "ar", content)

	def test_the_registry_declares_the_page_title_content_and_seo_fields(self):
		self.assertEqual(
			get_translatable_fields(PAGE), {"title", "content", "meta_title", "meta_description"}
		)

	def test_a_translated_page_renders_in_arabic(self):
		context = self.run_context(self.page.route, lang="ar")

		self.assertEqual((context.page_title, context.content), ("سياسة الإرجاع", ARABIC_CONTENT))
		self.assertEqual(
			context.breadcrumbs, [{"label": "سياسة الإرجاع", "href": f"/ar/page/{self.page.route}"}]
		)
		self.assertEqual(
			(context.seo["title"], context.seo["description"]), ("الإرجاع", "سياسة الإرجاع لدينا")
		)

	def test_the_sdk_returns_the_translated_page_with_its_source_handle(self):
		use_storefront_language(self, "ar")
		page = shop.get_page(self.page.route)

		self.assertEqual(page["handle"], self.page.route)
		self.assertEqual((page["title"], page["body_html"]), ("سياسة الإرجاع", ARABIC_CONTENT))
		self.assertEqual(
			page["seo"],
			{
				"title": "الإرجاع",
				"custom_title": True,
				"description": "سياسة الإرجاع لدينا",
				"noindex": False,
			},
		)
		listed = next(link for link in shop.list_pages() if link["handle"] == self.page.route)
		self.assertEqual(listed["title"], "سياسة الإرجاع")

	def test_the_default_language_shows_the_source(self):
		use_storefront_language(self, "en")
		page = shop.get_page(self.page.route)

		self.assertEqual((page["title"], page["body_html"]), (self.page.name, ENGLISH_CONTENT))
		self.assertEqual(
			(page["seo"]["title"], page["seo"]["description"]), ("Returns", "Our returns policy")
		)
		self.assertEqual(self.run_context(self.page.route).page_title, self.page.name)

	def test_an_untranslated_page_falls_back_to_frappe_translation_then_the_source(self):
		plain = self.make_page(title=f"Shipping {self.tag}")
		frappe_translated = self.make_page(title=f"Sizes {self.tag}")
		translation = frappe.get_doc(
			{
				"doctype": "Translation",
				"language": "ar",
				"source_text": frappe_translated.name,
				"translated_text": "دليل المقاسات",
			}
		).insert()
		self.addCleanup(frappe.delete_doc, "Translation", translation.name, force=True)

		use_storefront_language(self, "ar")
		plain_page = shop.get_page(plain.route)

		self.assertEqual((plain_page["title"], plain_page["body_html"]), (plain.name, ENGLISH_CONTENT))
		self.assertEqual(
			plain_page["seo"],
			{"title": plain.name, "custom_title": False, "description": "", "noindex": False},
		)
		dictionary_page = shop.get_page(frappe_translated.route)
		self.assertEqual(dictionary_page["title"], "دليل المقاسات")
		self.assertEqual(
			(dictionary_page["seo"]["title"], dictionary_page["seo"]["custom_title"]),
			("دليل المقاسات", False),
		)
		self.assertEqual(self.run_context(plain.route, lang="ar").breadcrumbs[0]["label"], plain.name)

	def test_the_sdk_and_the_www_heading_show_the_page_title_and_seo_keeps_the_meta_title(self):
		page = self.make_page(title=f"Care {self.tag}", meta_title="Care guide")
		register(PAGE, page.name, "title", "ar", "العناية")

		use_storefront_language(self, "ar")
		sdk_page = shop.get_page(page.route)
		self.assertEqual(sdk_page["title"], "العناية")
		self.assertEqual((sdk_page["seo"]["title"], sdk_page["seo"]["custom_title"]), ("Care guide", True))
		context = self.run_context(page.route, lang="ar")
		self.assertEqual((context.page_title, context.seo["title"]), ("العناية", "Care guide"))

	def test_pages_with_the_same_title_list_by_handle(self):
		later = self.make_page(title=f"Later {self.tag}", route=f"b-same-{self.tag.lower()}")
		earlier = self.make_page(title=f"Earlier {self.tag}", route=f"a-same-{self.tag.lower()}")
		for page in (later, earlier):
			register(PAGE, page.name, "title", "ar", f"نفس {self.tag}")

		use_storefront_language(self, "ar")
		handles = [link["handle"] for link in shop.list_pages() if link["title"] == f"نفس {self.tag}"]
		self.assertEqual(handles, [earlier.route, later.route])

	def test_translated_content_follows_the_request_language_not_frappe_lang(self):
		page = self.make_page(title=f"Lang {self.tag}")
		register(PAGE, page.name, "content", "ar", ARABIC_CONTENT)

		self.assertEqual(self.run_context(page.route, lang="ar", frappe_lang="en").content, ARABIC_CONTENT)
		self.assertEqual(self.run_context(page.route, lang="en", frappe_lang="ar").content, ENGLISH_CONTENT)

	def test_an_arabic_translation_is_unused_when_arabic_is_the_default_language(self):
		use_storefront_languages(self, "ar", published=("ar", "en"))
		page = self.make_page(title=f"Default {self.tag}")
		register(PAGE, page.name, "content", "ar", ARABIC_CONTENT)

		self.assertEqual(self.run_context(page.route, lang="ar").content, ENGLISH_CONTENT)

	def test_a_content_translation_wins_over_a_frappe_dictionary_translation(self):
		page = self.make_page(title=f"Dictionary {self.tag}")
		translation = frappe.get_doc(
			{
				"doctype": "Translation",
				"language": "ar",
				"source_text": ENGLISH_CONTENT,
				"translated_text": "<p>قاموس</p>",
			}
		).insert()
		self.addCleanup(frappe.delete_doc, "Translation", translation.name, force=True)

		self.assertEqual(self.run_context(page.route, lang="ar").content, "<p>قاموس</p>")
		register(PAGE, page.name, "content", "ar", ARABIC_CONTENT)
		self.assertEqual(self.run_context(page.route, lang="ar").content, ARABIC_CONTENT)

	def test_translated_content_is_sanitized_like_the_source(self):
		unsafe = '<p onclick="steal()">مرحبا</p><script>steal()</script>'
		page = self.make_page(title=f"Unsafe {self.tag}", content=unsafe)
		register(PAGE, page.name, "content", "ar", unsafe)

		source = self.run_context(page.route).content
		translated = self.run_context(page.route, lang="ar").content
		self.assertEqual(translated, source)
		self.assertNotIn("script", translated)
		self.assertNotIn("onclick", translated)

	def test_deleting_a_page_deletes_its_translations(self):
		frappe.delete_doc(PAGE, self.page.name)

		self.assertFalse(
			frappe.db.exists(
				"Content Translation", {"reference_doctype": PAGE, "reference_name": self.page.name}
			)
		)


class TestShopWebPageThemedRoute(IntegrationTestCase):
	def test_the_patch_seeds_the_themed_page_route(self):
		frappe.db.delete("Shop Themed Route", {"template_path": "pages/shop_web_page.html"})
		frappe.get_single("Shop Theme Settings").reload()

		seed_shop_web_page_route()

		patterns = {row.url_pattern for row in frappe.get_single("Shop Theme Settings").routes}
		self.assertIn(r"^page/(?P<route>.+)$", patterns)
