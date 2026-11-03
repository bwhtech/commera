# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin.theme_layout import discard, get_editor, publish, save_draft
from commera.shop_themes.doctype.shop_theme.shop_theme import clear_theme_cache, get_theme_context
from commera.shop_themes.sections import clear_layout_cache, get_page_layout, get_theme_json

PARENT = "Commera Starter"
CHILD = "ZZ Inherit Child"
GRANDCHILD = "ZZ Inherit Grandchild"
PAGE = "index"


class TestThemeLayoutInheritance(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.clear_cache)
		self.addCleanup(clear_theme_cache)
		self.addCleanup(frappe.db.rollback)

		for theme_name, parent_theme in ((CHILD, PARENT), (GRANDCHILD, CHILD)):
			frappe.get_doc(
				doctype="Shop Theme",
				theme_name=theme_name,
				theme_type="Sections",
				parent_theme=parent_theme,
				module="Shop Themes",
			).db_insert()
		clear_theme_cache()

		frappe.db.delete("Theme Layout", {"theme": PARENT, "page": PAGE})
		for theme_name in (PARENT, CHILD, GRANDCHILD):
			clear_layout_cache(theme_name, PAGE)
			self.addCleanup(clear_layout_cache, theme_name, PAGE)

		self.file_layout = get_theme_json(get_theme_context(PARENT)["dirs"], f"layouts/{PAGE}.json")

	def reordered_layout(self, shift):
		sections = self.file_layout["sections"]
		return {**self.file_layout, "sections": sections[shift:] + sections[:shift]}

	def rendered_layout(self, theme_name):
		return get_page_layout(get_theme_context(theme_name), PAGE)

	def test_a_child_renders_its_parents_published_layout(self):
		self.assertEqual(self.rendered_layout(CHILD), self.file_layout)

		publish(PARENT, PAGE, self.reordered_layout(1))

		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(1))

	def test_a_childs_own_published_layout_wins(self):
		publish(PARENT, PAGE, self.reordered_layout(1))
		publish(CHILD, PAGE, self.reordered_layout(2))

		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(2))
		self.assertEqual(self.rendered_layout(PARENT), self.reordered_layout(1))

	def test_a_grandchild_inherits_the_nearest_published_ancestor(self):
		publish(PARENT, PAGE, self.reordered_layout(1))
		self.assertEqual(self.rendered_layout(GRANDCHILD), self.reordered_layout(1))

		publish(CHILD, PAGE, self.reordered_layout(2))
		self.assertEqual(self.rendered_layout(GRANDCHILD), self.reordered_layout(2))

	def test_a_parent_publishing_again_reaches_a_child_already_cached(self):
		publish(PARENT, PAGE, self.reordered_layout(1))
		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(1))

		publish(PARENT, PAGE, self.reordered_layout(3))

		self.assertEqual(self.rendered_layout(CHILD), self.reordered_layout(3))

	def test_the_editor_opens_an_unedited_child_page_on_the_parents_layout(self):
		publish(PARENT, PAGE, self.reordered_layout(1))

		editor = get_editor(CHILD, PAGE)

		self.assertIsNone(editor["published_layout"])
		self.assertEqual(editor["default_layout"], self.reordered_layout(1))
		self.assertEqual(editor["draft_layout"], self.reordered_layout(1))
		self.assertFalse(editor["has_unpublished_changes"])

		save_draft(CHILD, PAGE, self.reordered_layout(2))
		discarded = discard(CHILD, PAGE)

		self.assertEqual(discarded["draft_layout"], self.reordered_layout(1))
		self.assertFalse(discarded["has_unpublished_changes"])
