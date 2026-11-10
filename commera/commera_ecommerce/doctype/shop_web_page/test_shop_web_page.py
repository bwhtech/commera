# Copyright (c) 2026, ivend and Contributors
# Merchant-authored content pages: routing, language fallback and the guest 404.

import frappe
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.patches.seed_shop_web_page_route import execute as seed_shop_web_page_route
from commera.www.shop_web_page import index as www_shop_web_page

ENGLISH_CONTENT = "<p>Free returns within 30 days.</p>"
ARABIC_CONTENT = "<p>إرجاع مجاني خلال 30 يومًا.</p>"


class TestShopWebPage(IntegrationTestCase):
	def setUp(self):
		self.tag = frappe.generate_hash(length=8)
		self.saved_request = getattr(frappe.local, "request", None)
		self.saved_lang = frappe.local.lang
		self.addCleanup(self.restore_locals)
		self.addCleanup(frappe.set_user, frappe.session.user)

	def restore_locals(self):
		frappe.local.request = self.saved_request
		frappe.local.lang = self.saved_lang

	def make_page(self, title=None, **fields):
		page = frappe.new_doc("Shop Web Page")
		page.name = title or f"Returns Policy {self.tag}"
		page.content = ENGLISH_CONTENT
		page.update(fields)
		return page.insert()

	def run_context(self, route, lang="en"):
		frappe.local.lang = lang
		frappe.local.request = Request(EnvironBuilder(path=f"/{lang}/page/{route}").get_environ())
		frappe.form_dict.route = route
		self.addCleanup(frappe.form_dict.pop, "route", None)

		context = frappe._dict()
		www_shop_web_page.get_context(context)
		return context

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
		page = self.make_page(content_ar=ARABIC_CONTENT)
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


class TestShopWebPageThemedRoute(IntegrationTestCase):
	def test_the_patch_seeds_the_themed_page_route(self):
		frappe.db.delete("Shop Themed Route", {"template_path": "pages/shop_web_page.html"})
		frappe.get_single("Shop Theme Settings").reload()

		seed_shop_web_page_route()

		patterns = {row.url_pattern for row in frappe.get_single("Shop Theme Settings").routes}
		self.assertIn(r"^page/(?P<route>.+)$", patterns)
