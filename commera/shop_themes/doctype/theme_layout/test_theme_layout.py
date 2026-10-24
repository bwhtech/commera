# Copyright (c) 2026, BWH Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.jinja import get_jenv

from commera.shop_themes.doctype.theme_layout.theme_layout import (
	MAX_SECTIONS,
	get_layout,
	get_saved_layout,
	save_theme_layout,
)
from commera.shop_themes.tests.theme_fixtures import ThemeFixtureMixin
from commera.shop_themes.theme_resolver import get_theme_environment

IGNORE_TEST_RECORD_DEPENDENCIES = ["Shop Theme", "User"]


def banner(section_id="banner", **section):
	return {"id": section_id, "type": "banner", "settings": {}, **section}


def hero(blocks=(), section_id="hero", **settings):
	return {"id": section_id, "type": "hero", "settings": settings, "blocks": list(blocks)}


def slide(block_id, **block):
	return {"id": block_id, "type": "slide", "settings": {}, **block}


class IntegrationTestThemeLayout(ThemeFixtureMixin, IntegrationTestCase):
	def setUp(self):
		self.add_fixture_theme()

	def save(self, *sections, template="index"):
		return save_theme_layout(self.theme_name, template, {"sections": list(sections)})

	def render_index(self):
		theme_env = get_theme_environment(get_jenv(), self.theme_dirs)
		return theme_env.from_string('{{ render_layout("index") }}').render()

	def assert_rejected(self, sections, expected_message, template="index"):
		with self.assertRaises(frappe.ValidationError) as context:
			self.save(*sections, template=template)
		self.assertIn(expected_message, str(context.exception))

	def test_valid_layouts_save_as_one_row_per_section(self):
		theme_layout = self.save(
			hero([slide("slide-1", settings={"title": {"en": "Hi", "ar": "مرحبا"}})]),
			banner(settings={"heading": "Sale"}, disabled=True),
			{"id": "apps", "type": "app_ready", "blocks": [{"id": "a1", "type": "app:shop/size_chart"}]},
		)
		self.assertEqual(
			[(row.idx, row.section_id, row.section_type, row.hidden) for row in theme_layout.sections],
			[(1, "hero", "hero", 0), (2, "banner", "banner", 1), (3, "apps", "app_ready", 0)],
		)
		self.save({"id": "p", "type": "product_only"}, template="product.special")
		self.save({"id": "bar", "type": "header_bar"}, template="group:header")

	def test_params_drop_unknown_keys_coerce_types_and_fill_defaults(self):
		theme_layout = self.save(hero(count="7", autoplay="0", retired="x", height="small"))
		self.assertEqual(
			frappe.parse_json(theme_layout.sections[0].params),
			{
				"heading": {"en": "Welcome", "ar": "أهلا"},
				"height": "small",
				"count": 7,
				"autoplay": False,
				"link": "",
				"accent": "",
				"collection": "",
			},
		)

	def test_blocks_keep_their_shape_with_resolved_settings(self):
		theme_layout = self.save(hero([slide("s1", disabled=1, settings={"title": "One", "old": 1})]))
		self.assertEqual(
			frappe.parse_json(theme_layout.sections[0].blocks),
			[{"id": "s1", "type": "slide", "settings": {"title": "One"}, "disabled": True}],
		)

	def test_an_unknown_template_is_rejected(self):
		self.assert_rejected([], "home is not a layout template", template="home")
		self.assert_rejected([], "settings is not a layout template", template="settings")

	def test_row_errors_name_the_row(self):
		self.assert_rejected([banner(), {"id": "x", "type": "retired"}], "Row #2: Section Type retired")
		self.assert_rejected([banner("bad id!")], "Row #1: bad id! is not a valid id")
		self.assert_rejected([hero([slide("hero")])], "Row #1: The id hero is used more than once")
		self.assert_rejected(
			[hero([{"id": "q", "type": "quote"}])], "Row #1: Blocks: q has an unknown type quote"
		)
		self.assert_rejected(
			[hero([{"id": "a", "type": "app:shop/size_chart"}])], "hero does not accept app blocks"
		)
		self.assert_rejected([{**hero(), "blocks": {"id": "x"}}], "Row #1: Blocks must be a list")
		self.assert_rejected([hero([slide("s1", settings="x")])], "Row #1: s1: settings must be an object")

	def test_invalid_json_in_a_row_is_rejected(self):
		theme_layout = self.save(banner())
		theme_layout.sections[0].params = "{not json"
		with self.assertRaises(frappe.ValidationError) as context:
			theme_layout.save()
		self.assertIn("Row #1: Params is not valid JSON", str(context.exception))

	def test_limits_are_enforced(self):
		self.assert_rejected(
			[banner(f"banner-{index}") for index in range(MAX_SECTIONS + 1)],
			f"at most {MAX_SECTIONS} sections",
		)
		self.assert_rejected(
			[hero([slide(f"slide-{index}") for index in range(5)])], "hero can have at most 4 blocks"
		)

	def test_placement_is_enforced(self):
		self.assert_rejected([{"id": "bar", "type": "header_bar"}], "belongs in the header group")
		self.assert_rejected([banner()], "cannot be placed in the header group", template="group:header")
		self.assert_rejected([{"id": "p", "type": "product_only"}], "cannot be placed on index pages")
		self.assert_rejected([banner()], "The main section cannot be removed", template="page")
		self.save({"id": "main", "type": "main"}, template="page.contact")

	def test_invalid_setting_values_name_the_field(self):
		cases = (
			({"height": "huge"}, "Row #1: Params: height has an invalid value"),
			({"count": 11}, "Params: count has an invalid value"),
			({"count": True}, "Params: count has an invalid value"),
			({"autoplay": "yes"}, "Params: autoplay has an invalid value"),
			({"accent": "red"}, "Params: accent has an invalid value"),
			({"heading": {"fr": "Bonjour"}}, "Params: heading has an invalid value"),
			({"link": "javascript:alert(1)"}, "Params: link has an invalid value"),
		)
		for settings, expected_message in cases:
			with self.subTest(settings=settings):
				self.assert_rejected([hero(**settings)], expected_message)

	def test_link_values_must_exist(self):
		existing_group = frappe.get_all("Item Group", pluck="name", limit=1)[0]
		self.save(hero(collection=existing_group))
		self.assert_rejected(
			[hero(collection="No Such Item Group")],
			"Params: collection links to Item Group No Such Item Group, which does not exist",
		)

	def test_a_second_row_for_the_same_theme_and_template_is_refused(self):
		self.save(banner())
		duplicate = frappe.new_doc("Theme Layout", theme=self.theme_name, template="index")
		self.assertRaises(frappe.DuplicateEntryError, duplicate.insert)

	def test_the_database_refuses_a_duplicate_that_skips_validation(self):
		self.save(banner())
		duplicate = frappe.new_doc("Theme Layout", theme=self.theme_name, template="index")
		duplicate.set_new_name()
		self.assertRaises((frappe.UniqueValidationError, frappe.DuplicateEntryError), duplicate.db_insert)

	def test_saving_again_replaces_the_sections_of_the_same_row(self):
		first = self.save(banner())
		second = self.save(banner("other"))
		self.assertEqual(first.name, second.name)
		self.assertEqual([row.section_id for row in second.sections], ["other"])

	def test_an_absent_or_empty_row_renders_the_default_layout_file(self):
		self.assertIsNone(get_saved_layout(self.theme_name, "index"))
		self.assertEqual(get_layout(self.theme_context, "index")["sections"][0]["id"], "hero")
		self.assertIn('id="section-hero"', self.render_index())

		self.save()
		self.assertIsNone(get_saved_layout(self.theme_name, "index"))
		self.assertIn('id="section-hero"', self.render_index())

	def test_saved_sections_render_in_row_order_and_skip_hidden_rows(self):
		self.save(
			banner("second", settings={"heading": "B"}), banner("first", disabled=True), banner("third")
		)
		html = self.render_index()
		self.assertIn('id="section-second"', html)
		self.assertIn('id="section-third"', html)
		self.assertNotIn("section-first", html)
		self.assertLess(html.index("section-second"), html.index("section-third"))

	def test_saving_clears_the_cached_layout(self):
		self.save(banner("first"))
		self.assertEqual(get_saved_layout(self.theme_name, "index")["sections"][0]["id"], "first")

		self.save(banner("second"))
		self.assertEqual(get_saved_layout(self.theme_name, "index")["sections"][0]["id"], "second")

	def test_a_rolled_back_save_does_not_stay_cached(self):
		self.save(banner("first"))
		self.assertTrue(get_saved_layout(self.theme_name, "index"))

		frappe.db.rollback()

		self.assertIsNone(get_saved_layout(self.theme_name, "index"))

	def test_deleting_the_row_falls_back_to_the_default_file(self):
		theme_layout = self.save(banner("live"))
		self.assertTrue(get_saved_layout(self.theme_name, "index"))
		theme_layout.delete()
		self.assertIsNone(get_saved_layout(self.theme_name, "index"))

	def test_a_website_manager_can_save_a_layout_and_a_website_user_cannot(self):
		self.addCleanup(frappe.set_user, "Administrator")
		manager = self.add_user("theme-layout-manager@example.com", "System User", ["Website Manager"])
		shopper = self.add_user("theme-layout-shopper@example.com", "Website User", [])

		frappe.set_user(manager)
		self.assertTrue(self.save(banner()).name)

		frappe.set_user(shopper)
		self.assertRaises(frappe.PermissionError, self.save, {"id": "main", "type": "main"}, template="page")
		self.assertFalse(frappe.has_permission("Theme Layout", "read"))

	def add_user(self, email, user_type, roles):
		user = frappe.new_doc("User")
		user.update({"email": email, "first_name": email.split("@")[0], "send_welcome_email": 0})
		for role in roles:
			user.append("roles", {"role": role})
		user.insert(ignore_permissions=True)
		user.db_set("user_type", user_type)
		return user.name
