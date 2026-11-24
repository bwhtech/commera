# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin.pages import PAGE_DOCTYPE, get_page_url
from commera.api.admin.theme import activate_theme
from commera.commera_ecommerce.doctype.commera_settings.footer.footer_preview import (
	STATIC_STOREFRONT_ROUTES,
	add_footer_link,
	add_footer_section,
	delete_footer_link,
	delete_footer_section,
	get_footer_editor_data,
	move_footer_link,
	rename_footer_section,
	reorder_footer_links,
	reorder_footer_sections,
	update_footer_link,
)
from commera.shop_themes.doctype.shop_theme.shop_theme import get_theme_context, resolve_active_theme
from commera.www.footer_editor_preview import COLOR_PATTERN, get_context


class TestFooterEditor(IntegrationTestCase):
	# IntegrationTestCase rolls back once per class (addClassCleanup), so each test must clean up after
	# itself or the next hits a duplicate Footer Section Config (autoname is field:section_title).
	SECTION_TITLES = ("Help", "About", "Contact", "Support")
	WEB_PAGE_ROUTES = ("footer-editor-test-page", "footer-editor-draft-page")

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		activate_theme("Summer Theme")

	def setUp(self):
		self.remove_test_documents()

	def tearDown(self):
		self.remove_test_documents()

	def remove_test_documents(self):
		settings = frappe.get_single("Commera Settings")
		settings.footer_sections = []
		settings.save()
		for title in self.SECTION_TITLES:
			if frappe.db.exists("Footer Section Config", title):
				frappe.delete_doc("Footer Section Config", title, force=True, ignore_permissions=True)
		for route in self.WEB_PAGE_ROUTES:
			for name in frappe.get_all(PAGE_DOCTYPE, filters={"route": route}, pluck="name"):
				frappe.delete_doc(PAGE_DOCTYPE, name, force=True, ignore_permissions=True)

	def link_row_name(self, section_name, index=0):
		section = frappe.get_doc("Footer Section Config", section_name)
		return section.footer_links[index].name

	def test_add_footer_section_creates_config_and_mapping(self):
		data = add_footer_section("Help")
		self.assertTrue(frappe.db.exists("Footer Section Config", "Help"))
		settings = frappe.get_single("Commera Settings")
		self.assertEqual([row.footer_section for row in settings.footer_sections], ["Help"])
		self.assertEqual([column["title"] for column in data["columns"]], ["Help"])

	def test_add_duplicate_title_rejected(self):
		add_footer_section("Help")
		with self.assertRaises(frappe.DuplicateEntryError):
			add_footer_section("Help")

	def test_rename_footer_section_updates_mapping(self):
		add_footer_section("Help")
		data = rename_footer_section("Help", "Support")

		settings = frappe.get_single("Commera Settings")
		self.assertEqual([row.footer_section for row in settings.footer_sections], ["Support"])
		self.assertEqual([column["name"] for column in data["columns"]], ["Support"])

	def test_delete_footer_section_cascades_links_and_mapping(self):
		add_footer_section("Help")
		add_footer_link("Help", "Privacy Policy", "/privacy-policy")

		data = delete_footer_section("Help")

		self.assertFalse(frappe.db.exists("Footer Section Config", "Help"))
		settings = frappe.get_single("Commera Settings")
		self.assertEqual(settings.footer_sections, [])
		self.assertEqual(data["columns"], [])

	def test_reorder_footer_sections(self):
		add_footer_section("Help")
		add_footer_section("About")

		data = reorder_footer_sections(["About", "Help"])

		self.assertEqual([column["name"] for column in data["columns"]], ["About", "Help"])

	def test_reorder_footer_sections_rejects_unknown_name(self):
		add_footer_section("Help")
		with self.assertRaises(frappe.ValidationError):
			reorder_footer_sections(["Help", "Nonexistent"])

	def test_add_footer_link(self):
		add_footer_section("Help")

		data = add_footer_link("Help", "Privacy Policy", "/privacy-policy")

		links = data["columns"][0]["links"]
		self.assertEqual([row["link_label"] for row in links], ["Privacy Policy"])
		self.assertEqual([row["link_url"] for row in links], ["/privacy-policy"])

	def test_update_footer_link(self):
		add_footer_section("Help")
		add_footer_link("Help", "Privacy Policy", "/privacy-policy")
		row_name = self.link_row_name("Help")

		data = update_footer_link("Help", row_name, "Privacy", "/privacy")

		links = data["columns"][0]["links"]
		self.assertEqual(links[0]["link_label"], "Privacy")
		self.assertEqual(links[0]["link_url"], "/privacy")

	def test_delete_footer_link(self):
		add_footer_section("Help")
		add_footer_link("Help", "Privacy Policy", "/privacy-policy")
		row_name = self.link_row_name("Help")

		data = delete_footer_link("Help", row_name)

		self.assertEqual(data["columns"][0]["links"], [])

	def test_reorder_footer_links(self):
		add_footer_section("Help")
		add_footer_link("Help", "A", "/a")
		add_footer_link("Help", "B", "/b")
		section = frappe.get_doc("Footer Section Config", "Help")
		row_names = [row.name for row in section.footer_links]

		data = reorder_footer_links("Help", list(reversed(row_names)))

		labels = [row["link_label"] for row in data["columns"][0]["links"]]
		self.assertEqual(labels, ["B", "A"])

	def test_move_footer_link_to_another_section(self):
		add_footer_section("Help")
		add_footer_section("Contact")
		add_footer_link("Help", "Privacy Policy", "/privacy-policy")
		row_name = self.link_row_name("Help")

		data = move_footer_link("Help", "Contact", row_name, 0)

		columns_by_name = {column["name"]: column for column in data["columns"]}
		self.assertEqual(columns_by_name["Help"]["links"], [])
		self.assertEqual(
			[row["link_label"] for row in columns_by_name["Contact"]["links"]], ["Privacy Policy"]
		)

	def test_move_footer_link_lands_at_target_index(self):
		add_footer_section("Help")
		add_footer_section("Contact")
		add_footer_link("Help", "Privacy Policy", "/privacy-policy")
		row_name = self.link_row_name("Help")
		add_footer_link("Contact", "Phone", "/contact/phone")
		add_footer_link("Contact", "Email", "/contact/email")

		data = move_footer_link("Help", "Contact", row_name, 1)

		columns_by_name = {column["name"]: column for column in data["columns"]}
		labels = [row["link_label"] for row in columns_by_name["Contact"]["links"]]
		self.assertEqual(labels, ["Phone", "Privacy Policy", "Email"])

	def test_move_footer_link_renumbers_source_link_order(self):
		add_footer_section("Help")
		add_footer_section("Contact")
		add_footer_link("Help", "A", "/a")
		add_footer_link("Help", "B", "/b")
		row_name = self.link_row_name("Help", index=0)

		move_footer_link("Help", "Contact", row_name, 0)

		remaining = frappe.get_doc("Footer Section Config", "Help")
		self.assertEqual([row.link_label for row in remaining.footer_links], ["B"])
		self.assertEqual([row.link_order for row in remaining.footer_links], [1])

	def make_shop_page(self, title, route, published):
		return frappe.get_doc(
			{
				"doctype": PAGE_DOCTYPE,
				"name": title,
				"content": "<p>hello</p>",
				"route": route,
				"published": published,
			}
		).insert()

	def test_page_list_unions_published_shop_pages_with_storefront_routes(self):
		page = self.make_shop_page("Footer Editor Test Page", "footer-editor-test-page", 1)
		self.make_shop_page("Footer Editor Draft Page", "footer-editor-draft-page", 0)

		routes = [row["route"] for row in get_footer_editor_data()["pages"]]

		self.assertIn(get_page_url(page.route), routes)
		self.assertNotIn(get_page_url("footer-editor-draft-page"), routes)
		for _label, static_route in STATIC_STOREFRONT_ROUTES:
			self.assertIn(static_route, routes)

	def test_color_pattern_accepts_valid_hex(self):
		self.assertTrue(COLOR_PATTERN.match("#fff"))
		self.assertTrue(COLOR_PATTERN.match("#ffffff"))

	def test_color_pattern_rejects_injection_and_non_hex(self):
		for value in ("#fff};x:expression(1)", "#fff\nx:expression(1)", "red", "#gggggg"):
			self.assertFalse(COLOR_PATTERN.match(value), repr(value))

	def test_add_footer_link_rejects_unsafe_url(self):
		add_footer_section("Help")
		for value in (
			"javascript:alert(1)",
			"JavaScript:alert(1)",
			"  javascript:alert(1)",
			"data:text/html,<script>alert(1)</script>",
			"vbscript:msgbox(1)",
		):
			with self.assertRaises(frappe.ValidationError, msg=repr(value)):
				add_footer_link("Help", "Evil", value)

	def test_update_footer_link_rejects_unsafe_url(self):
		add_footer_section("Help")
		add_footer_link("Help", "Privacy Policy", "/privacy-policy")
		row_name = self.link_row_name("Help")
		with self.assertRaises(frappe.ValidationError):
			update_footer_link("Help", row_name, "Privacy Policy", "javascript:alert(1)")

	def test_get_context_rejects_unsafe_url_and_escapes_text(self):
		original_form_dict = frappe.local.form_dict
		frappe.local.form_dict = frappe._dict(
			footer_logo="javascript:alert(1)",
			copyright_text="<script>alert(2)</script>",
			footer_bg_color="#fff};x:expression(1)",
		)
		try:
			context = frappe._dict()
			get_context(context)
			html = context.rendered_html
		finally:
			frappe.local.form_dict = original_form_dict

		self.assertNotIn("javascript:alert", html.lower())
		self.assertNotIn("expression(1)", html)
		self.assertNotIn("<script>alert(2)", html)
		self.assertIn("&lt;script&gt;alert(2)", html)

	def render_preview(self, **overrides):
		original_form_dict = frappe.local.form_dict
		frappe.local.form_dict = frappe._dict(lang="en", **overrides)
		try:
			context = frappe._dict()
			get_context(context)
			return context.rendered_html
		finally:
			frappe.local.form_dict = original_form_dict

	def test_preview_renders_the_active_theme_not_the_base_footer(self):
		"""The base template hardcodes columns the board does not manage, so a fallback disagrees with it."""
		html = self.render_preview()

		theme_name = resolve_active_theme()
		if not get_theme_context(theme_name)["dirs"]:
			self.skipTest("no theme active on this site")

		self.assertIn("page-wraper" if theme_name == "Summer Theme" else "theme-shop-default", html)

	def test_preview_hides_every_chrome_but_the_footer(self):
		html = self.render_preview()

		self.assertIn("<footer", html)
		self.assertNotIn("<header", html)
		self.assertNotIn("<nav", html)
		self.assertNotIn("breadcrumb", html)

	def test_preview_markup_is_balanced(self):
		"""The wrapper opens in one block and closes in another, so blanking the wrong one unscopes the footer."""
		html = self.render_preview()

		self.assertEqual(html.count("<div"), html.count("</div>"))

	def test_get_context_applies_accepted_overrides(self):
		original_form_dict = frappe.local.form_dict
		frappe.local.form_dict = frappe._dict(
			footer_logo="/files/preview-logo.png",
			copyright_text="Preview Copyright Line",
			footer_bg_color="#123456",
		)
		try:
			context = frappe._dict()
			get_context(context)
			html = context.rendered_html
		finally:
			frappe.local.form_dict = original_form_dict

		self.assertIn("/files/preview-logo.png", html)
		self.assertIn("Preview Copyright Line", html)
		self.assertIn("--ls-footer-bg: #123456", html)
