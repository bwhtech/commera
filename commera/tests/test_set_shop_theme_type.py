# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

import frappe
from frappe.modules.import_file import import_file_by_path
from frappe.tests import IntegrationTestCase

from commera.patches import set_shop_theme_type
from commera.shop_themes.doctype.shop_theme.shop_theme import clear_theme_cache

STARTER = "Commera Starter"


class TestSetShopThemeType(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(clear_theme_cache)
		self.addCleanup(frappe.db.rollback)

	def get_theme_types(self):
		return dict(frappe.get_all("Shop Theme", fields=["name", "theme_type"], as_list=True))

	def test_a_sections_theme_outside_summer_keeps_its_type(self):
		frappe.db.set_value("Shop Theme", STARTER, "theme_type", "Sections", update_modified=False)

		set_shop_theme_type.execute()

		theme_types = self.get_theme_types()
		self.assertEqual(theme_types[STARTER], "Sections")
		self.assertEqual(theme_types["Summer Theme"], "Sections")
		self.assertEqual(theme_types["Shop Default Theme"], "Classic")

	def test_migrate_restores_a_starter_the_old_patch_set_to_classic(self):
		frappe.db.set_value(
			"Shop Theme",
			STARTER,
			{"theme_type": "Classic", "modified": "2026-11-02 12:00:00"},
			update_modified=False,
		)

		set_shop_theme_type.execute()
		import_file_by_path(
			frappe.get_app_path("commera", "shop_themes", "shop_theme", "commera_starter", "commera_starter.json")
		)

		self.assertEqual(self.get_theme_types()[STARTER], "Sections")
