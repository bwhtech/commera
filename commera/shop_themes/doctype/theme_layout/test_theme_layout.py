# Copyright (c) 2026, BWH Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.jinja import get_jenv

from commera.shop_themes.layouts import (
	MAX_SECTIONS,
	get_layout,
	get_published_layout,
	layout_override,
	save_theme_layout,
	validate_layout,
)
from commera.shop_themes.tests.theme_fixtures import ThemeFixtureMixin
from commera.shop_themes.theme_resolver import get_theme_environment

IGNORE_TEST_RECORD_DEPENDENCIES = ["Shop Theme", "User"]


def banner(section_id="banner", **section):
	return {"id": section_id, "type": "banner", "settings": {}, **section}


def hero(blocks, section_id="hero"):
	return {"id": section_id, "type": "hero", "settings": {}, "blocks": blocks}


def slide(block_id, **block):
	return {"id": block_id, "type": "slide", "settings": {}, **block}


class IntegrationTestThemeLayout(ThemeFixtureMixin, IntegrationTestCase):
	def setUp(self):
		self.add_fixture_theme()

	def render_index(self):
		theme_env = get_theme_environment(get_jenv(), self.theme_dirs)
		return theme_env.from_string('{{ render_layout("index") }}').render()

	def assert_rejected(self, layout, expected_message, template="index"):
		errors = validate_layout(self.theme_dirs, template, layout)
		self.assertTrue(
			any(expected_message in error for error in errors),
			f"expected {expected_message!r} in {errors}",
		)

	def test_a_valid_layout_has_no_errors(self):
		layout = {
			"sections": [
				hero([slide("slide-1", settings={"title": {"en": "Hi", "ar": "مرحبا"}})]),
				banner(settings={"heading": "Sale"}),
				{"id": "apps", "type": "app_ready", "blocks": [{"id": "a1", "type": "app:shop/size_chart"}]},
			]
		}
		self.assertEqual(validate_layout(self.theme_dirs, "index", layout), [])
		self.assertEqual(
			validate_layout(
				self.theme_dirs, "product.special", {"sections": [{"id": "p", "type": "product_only"}]}
			),
			[],
		)
		self.assertEqual(
			validate_layout(
				self.theme_dirs, "group:header", {"sections": [{"id": "bar", "type": "header_bar"}]}
			),
			[],
		)

	def test_structure_errors_are_rejected(self):
		self.assertEqual(
			validate_layout(self.theme_dirs, "home", {"sections": []}), ["home is not a layout template"]
		)
		self.assert_rejected([], "A layout needs a sections list")
		self.assert_rejected({"sections": ["banner"]}, "Section 1 is not an object")
		self.assert_rejected({"sections": [banner("bad id!")]}, "bad id! is not a valid id")
		self.assert_rejected({"sections": [hero([slide("hero")])]}, "The id hero is used more than once")
		self.assert_rejected({"sections": [banner(disabled="yes")]}, "banner: disabled must be true or false")
		self.assert_rejected({"sections": [hero({"id": "x"})]}, "Section hero: blocks must be a list")

	def test_limits_are_enforced(self):
		too_many_sections = [banner(f"banner-{index}") for index in range(MAX_SECTIONS + 1)]
		self.assert_rejected({"sections": too_many_sections}, f"at most {MAX_SECTIONS} sections")
		too_many_blocks = [slide(f"slide-{index}") for index in range(5)]
		self.assert_rejected({"sections": [hero(too_many_blocks)]}, "Section hero can have at most 4 blocks")

	def test_unknown_types_are_rejected(self):
		self.assert_rejected(
			{"sections": [{"id": "x", "type": "retired"}]}, "Section x has an unknown type retired"
		)
		self.assert_rejected(
			{"sections": [hero([{"id": "q", "type": "quote"}])]},
			"Block q in section hero has an unknown type quote",
		)
		self.assert_rejected(
			{"sections": [hero([{"id": "a", "type": "app:shop/size_chart"}])]},
			"Section hero does not accept app blocks",
		)

	def test_placement_is_enforced(self):
		self.assert_rejected(
			{"sections": [{"id": "bar", "type": "header_bar"}]}, "belongs in the header group"
		)
		self.assert_rejected(
			{"sections": [banner()]}, "cannot be placed in the header group", template="group:header"
		)
		self.assert_rejected(
			{"sections": [{"id": "p", "type": "product_only"}]}, "cannot be placed on index pages"
		)
		self.assert_rejected({"sections": [banner()]}, "The main section cannot be removed", template="page")
		self.assertEqual(
			validate_layout(self.theme_dirs, "page.contact", {"sections": [{"id": "main", "type": "main"}]}),
			[],
		)

	def test_setting_values_are_type_checked(self):
		cases = (
			({"unknown": 1}, "hero: unknown setting unknown"),
			({"height": "huge"}, "hero: height has an invalid value"),
			({"count": 11}, "hero: count has an invalid value"),
			({"count": True}, "hero: count has an invalid value"),
			({"autoplay": 1}, "hero: autoplay has an invalid value"),
			({"accent": "red"}, "hero: accent has an invalid value"),
			({"heading": {"fr": "Bonjour"}}, "hero: heading has an invalid value"),
			({"link": {"en": "/x"}}, "hero: link has an invalid value"),
		)
		for settings, expected_message in cases:
			with self.subTest(settings=settings):
				self.assert_rejected(
					{"sections": [{"id": "hero", "type": "hero", "settings": settings}]}, expected_message
				)

		self.assert_rejected(
			{"sections": [hero([slide("s1", settings="x")])]}, "s1: settings must be an object"
		)

	def test_link_values_must_exist(self):
		existing_group = frappe.get_all("Item Group", pluck="name", limit=1)[0]
		layout = {"sections": [{"id": "hero", "type": "hero", "settings": {"collection": existing_group}}]}
		self.assertEqual(validate_layout(self.theme_dirs, "index", layout), [])
		layout["sections"][0]["settings"]["collection"] = "No Such Item Group"
		self.assert_rejected(
			layout, "hero: collection links to Item Group No Such Item Group, which does not exist"
		)

	def test_theme_settings_are_validated_against_settings_json(self):
		self.assertEqual(validate_layout(self.theme_dirs, "settings", {"settings": {"radius": 40}}), [])
		self.assert_rejected({"settings": {"radius": 41}}, "radius has an invalid value", template="settings")
		self.assert_rejected({"settings": {"font": "Inter"}}, "unknown setting font", template="settings")
		self.assert_rejected({"sections": []}, "Theme settings need a settings object", template="settings")

	def test_saving_an_invalid_layout_throws(self):
		with self.assertRaises(frappe.ValidationError):
			save_theme_layout(self.theme_name, "index", {"sections": [{"id": "x", "type": "retired"}]})
		with self.assertRaises(frappe.ValidationError):
			save_theme_layout(self.theme_name, "home", {"sections": []})

	def test_a_second_row_for_the_same_theme_and_template_is_refused(self):
		save_theme_layout(self.theme_name, "index", {"sections": [banner()]})
		duplicate = frappe.new_doc("Theme Layout")
		duplicate.update({"theme": self.theme_name, "template": "index", "layout": '{"sections": []}'})
		self.assertRaises(frappe.DuplicateEntryError, duplicate.insert)

	def test_the_database_refuses_a_duplicate_that_skips_validation(self):
		save_theme_layout(self.theme_name, "index", {"sections": [banner()]})
		duplicate = frappe.new_doc("Theme Layout")
		duplicate.update({"theme": self.theme_name, "template": "index"})
		duplicate.set_new_name()
		self.assertRaises((frappe.UniqueValidationError, frappe.DuplicateEntryError), duplicate.db_insert)

	def test_saving_again_updates_the_same_row(self):
		first = save_theme_layout(self.theme_name, "index", {"sections": [banner()]})
		second = save_theme_layout(self.theme_name, "index", {"sections": []})
		self.assertEqual(first.name, second.name)

	def test_an_absent_row_renders_the_default_layout_file(self):
		self.assertIsNone(get_published_layout(self.theme_name, "index"))
		self.assertEqual(get_layout(self.theme_context, "index")["sections"][0]["id"], "hero")
		self.assertIn('id="section-hero"', self.render_index())

	def test_the_published_layout_renders_and_the_draft_does_not(self):
		save_theme_layout(self.theme_name, "index", {"sections": [banner("draft_banner")]})
		self.assertIn('id="section-hero"', self.render_index())
		self.assertNotIn("draft_banner", self.render_index())

		theme_layout = save_theme_layout(
			self.theme_name, "index", {"sections": [banner("live_banner")]}, publish=True
		)
		self.assertIn('id="section-live_banner"', self.render_index())
		self.assertEqual(theme_layout.published_by, "Administrator")
		self.assertTrue(theme_layout.published_on)

		save_theme_layout(self.theme_name, "index", {"sections": [banner("next_draft")]})
		html = self.render_index()
		self.assertIn('id="section-live_banner"', html)
		self.assertNotIn("next_draft", html)

	def test_saving_clears_the_cached_published_layout(self):
		save_theme_layout(self.theme_name, "index", {"sections": [banner("first")]}, publish=True)
		self.assertEqual(get_published_layout(self.theme_name, "index")["sections"][0]["id"], "first")

		save_theme_layout(self.theme_name, "index", {"sections": [banner("second")]}, publish=True)
		self.assertEqual(get_published_layout(self.theme_name, "index")["sections"][0]["id"], "second")

	def test_a_rolled_back_save_does_not_stay_cached(self):
		save_theme_layout(self.theme_name, "index", {"sections": [banner("first")]}, publish=True)
		self.assertTrue(get_published_layout(self.theme_name, "index"))

		frappe.db.rollback()

		self.assertIsNone(get_published_layout(self.theme_name, "index"))

	def test_deleting_the_row_falls_back_to_the_default_file(self):
		theme_layout = save_theme_layout(
			self.theme_name, "index", {"sections": [banner("live")]}, publish=True
		)
		self.assertTrue(get_published_layout(self.theme_name, "index"))
		theme_layout.delete()
		self.assertIsNone(get_published_layout(self.theme_name, "index"))

	def test_a_layout_override_renders_in_place_of_the_published_layout(self):
		save_theme_layout(self.theme_name, "index", {"sections": [banner("live")]}, publish=True)
		with layout_override("index", {"sections": [banner("preview")]}):
			self.assertIn('id="section-preview"', self.render_index())
		self.assertIn('id="section-live"', self.render_index())

	def test_a_website_manager_can_save_a_layout_and_a_website_user_cannot(self):
		self.addCleanup(frappe.set_user, "Administrator")
		manager = self.add_user("theme-layout-manager@example.com", "System User", ["Website Manager"])
		shopper = self.add_user("theme-layout-shopper@example.com", "Website User", [])

		frappe.set_user(manager)
		self.assertTrue(save_theme_layout(self.theme_name, "index", {"sections": [banner()]}).name)

		frappe.set_user(shopper)
		self.assertRaises(
			frappe.PermissionError, save_theme_layout, self.theme_name, "page", {"sections": []}
		)
		self.assertFalse(frappe.has_permission("Theme Layout", "read"))

	def add_user(self, email, user_type, roles):
		user = frappe.new_doc("User")
		user.update({"email": email, "first_name": email.split("@")[0], "send_welcome_email": 0})
		for role in roles:
			user.append("roles", {"role": role})
		user.insert(ignore_permissions=True)
		user.db_set("user_type", user_type)
		return user.name
