# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

"""The storefront nav reads one data source, and the templates must not grow a second one."""

import re
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

from commera.commera_ecommerce.doctype.commera_settings.navbar import navbar_manager
from commera.shop_data import get_category_facets, get_header_data, get_storefront_menu
from commera.tests import delete_menu_entries

APP_ROOT = Path(frappe.get_app_path("commera"))

# Anything that reaches the database from inside a template.
QUERY_CALL = re.compile(r"frappe\.(?:db\.)?(?:get_all|get_list|get_doc|get_cached_doc|get_value|sql)\b")

PREFIX = "Test Nav"


def nav_template_paths():
	"""Every template that renders navigation, desktop or mobile."""
	paths = [
		APP_ROOT / "templates" / "includes" / "header.html",
		APP_ROOT / "templates" / "macros" / "navigation_menu.html",
	]
	paths += sorted((APP_ROOT / "templates" / "components").glob("*nav*.html"))
	return [path for path in paths if path.exists()]


class TestStorefrontNav(IntegrationTestCase):
	def setUp(self):
		self.tag = frappe.generate_hash(length=8)
		frappe.local.commera_storefront_menu = None

	def tearDown(self):
		delete_menu_entries({"name": ["like", f"{PREFIX}%"]})
		frappe.db.delete("Item Group", {"name": ["like", f"{PREFIX}%"]})
		frappe.local.commera_storefront_menu = None

	def make_item_group(self, name):
		return (
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": name,
					"custom_displayname": name,
					"is_group": 0,
				}
			)
			.insert()
			.name
		)

	def test_the_nav_templates_exist_to_be_checked(self):
		"""Without this the grep below would pass vacuously if the templates were ever renamed."""
		found = {path.name for path in nav_template_paths()}
		self.assertIn("header.html", found)
		self.assertIn("navigation_menu.html", found)

	def test_no_nav_template_queries_for_its_own_data(self):
		offenders = []
		for path in nav_template_paths():
			for number, line in enumerate(path.read_text().splitlines(), start=1):
				if QUERY_CALL.search(line):
					offenders.append(f"{path.relative_to(APP_ROOT)}:{number}: {line.strip()[:100]}")

		self.assertEqual(
			offenders,
			[],
			"a nav template queries for its own data; move it into commera/shop_data.py so a theme "
			"that overrides the template still renders the menu the shop owner built",
		)

	def test_the_grep_would_actually_catch_a_query(self):
		"""Guard against a regex that matches nothing — the check above must fire on the line it targets."""
		self.assertTrue(QUERY_CALL.search("{% set rows = frappe.get_all('Brand') %}"))
		self.assertTrue(QUERY_CALL.search("{% set rows = frappe.db.get_all('Ecommerce Category') %}"))
		self.assertIsNone(QUERY_CALL.search("{{ nav_menu(header_data.navigation_menu) }}"))

	def test_header_data_carries_the_menu_and_reuses_the_request_cache(self):
		tab = navbar_manager.create_node("", f"{PREFIX} Tab {self.tag}").name

		header_data = get_header_data()

		self.assertIn(tab, [node["name"] for node in header_data.navigation_menu])
		self.assertEqual(len(header_data.navigation_categories), len(header_data.navigation_menu))
		# Header, drawer and sidebar each read the menu, so the second read must be cached, not requeried.
		self.assertIs(get_storefront_menu(), header_data.navigation_menu)

	def test_a_hidden_tab_never_reaches_the_storefront_menu(self):
		tab = navbar_manager.create_node("", f"{PREFIX} Hidden {self.tag}").name
		frappe.local.commera_storefront_menu = None

		navbar_manager.set_visibility(tab, 0)
		frappe.local.commera_storefront_menu = None

		self.assertNotIn(tab, [node["name"] for node in get_storefront_menu()])

	def test_featured_brands_are_deduped_in_first_appearance_order(self):
		for brand in (f"{PREFIX} B1 {self.tag}", f"{PREFIX} B2 {self.tag}"):
			if not frappe.db.exists("Brand", brand):
				frappe.get_doc({"doctype": "Brand", "brand": brand}).insert()
		self.addCleanup(frappe.db.delete, "Brand", {"name": ["like", f"{PREFIX}%"]})

		tab = navbar_manager.create_node("", f"{PREFIX} Brands {self.tag}").name
		navbar_manager.create_node(tab, f"{PREFIX} Second", "Brand", f"{PREFIX} B2 {self.tag}")
		navbar_manager.create_node(tab, f"{PREFIX} First", "Brand", f"{PREFIX} B1 {self.tag}")
		# Same brand again on another arm: it must not appear twice.
		navbar_manager.create_node(tab, f"{PREFIX} Repeat", "Brand", f"{PREFIX} B2 {self.tag}")
		frappe.local.commera_storefront_menu = None

		names = [brand.name for brand in get_header_data().featured_brands]

		self.assertEqual(
			[name for name in names if name.startswith(PREFIX)],
			[f"{PREFIX} B2 {self.tag}", f"{PREFIX} B1 {self.tag}"],
		)

	def test_category_facets_key_every_tab_and_carry_the_item_group(self):
		shirts = self.make_item_group(f"{PREFIX} Shirts {self.tag}")
		belts = self.make_item_group(f"{PREFIX} Belts {self.tag}")
		tab = navbar_manager.create_node("", f"{PREFIX} Men {self.tag}").name
		navbar_manager.create_node(tab, f"{PREFIX} Tops", "Item Group", [shirts])
		navbar_manager.create_node(tab, f"{PREFIX} Belts Tab", "Item Group", [belts])
		frappe.local.commera_storefront_menu = None

		all_tabs = get_category_facets("")
		self.assertIn(f"{PREFIX} Men {self.tag}", all_tabs)
		facets = all_tabs[f"{PREFIX} Men {self.tag}"]
		self.assertEqual({facet["item_groups"][0] for facet in facets}, {shirts, belts})
		self.assertTrue(all(facet["is_leaf"] for facet in facets))

		# Selecting the tab by its entry name still keys the sidebar by the label a shopper reads.
		one_tab = get_category_facets(tab)
		self.assertEqual(list(one_tab), [f"{PREFIX} Men {self.tag}"])
		self.assertEqual(one_tab[f"{PREFIX} Men {self.tag}"], all_tabs[f"{PREFIX} Men {self.tag}"])
		self.assertEqual(get_category_facets(f"No Such Tab {self.tag}"), {})

	def test_a_heading_with_no_item_group_never_becomes_a_facet(self):
		"""A Brand or URL entry links no item group, so its facet would filter on the empty string."""
		tab = navbar_manager.create_node("", f"{PREFIX} Mixed {self.tag}").name
		navbar_manager.create_node(tab, f"{PREFIX} Just A Heading")
		navbar_manager.create_node(tab, f"{PREFIX} Off Site", "URL", "https://example.com")
		frappe.local.commera_storefront_menu = None

		self.assertEqual(get_category_facets("")[f"{PREFIX} Mixed {self.tag}"], [])
