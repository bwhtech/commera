import json
from pathlib import Path

import frappe
from frappe.desk.doctype.sidebar.sidebar import get_sidebar_bases
from frappe.tests import IntegrationTestCase

MODULES = ("Commera Ecommerce", "Shop Themes", "Discounts", "Shipping")


def read_shipped_sidebar(module: str) -> dict:
	folder = frappe.scrub(module)
	path = Path(frappe.get_module_path(module)) / "sidebar" / folder / f"{folder}.json"
	return json.loads(path.read_text())


class TestDeskSidebars(IntegrationTestCase):
	def test_the_desk_uses_the_shipped_sidebar(self):
		bases = get_sidebar_bases(list(MODULES))
		for module in MODULES:
			self.assertFalse(bases[module].computed, f"{module} fell back to a computed sidebar")

	def test_every_link_opens_an_existing_record(self):
		for module in MODULES:
			for item in read_shipped_sidebar(module)["items"]:
				if item["type"] != "Link":
					continue
				self.assertTrue(
					frappe.db.exists(item["link_type"], item["link_to"]),
					f"{module}: {item['link_type']} {item['link_to']} does not exist",
				)

	def test_every_doctype_of_the_module_is_listed(self):
		for module in MODULES:
			listed = {
				item["link_to"]
				for item in read_shipped_sidebar(module)["items"]
				if item["type"] == "Link" and item["link_type"] == "DocType"
			}
			doctypes = frappe.get_all(
				"DocType",
				filters={"module": module, "istable": 0, "custom": 0, "read_only": 0},
				pluck="name",
			)
			self.assertEqual(sorted(set(doctypes) - listed), [], f"{module} sidebar leaves these out")

	def test_every_top_level_row_has_an_icon(self):
		# Rows inside a group draw no icon in the desk, so only top-level rows and groups need one.
		for module in MODULES:
			sidebar = read_shipped_sidebar(module)
			self.assertTrue(sidebar["header_icon"], f"{module} has no header icon")
			for item in sidebar["items"]:
				if not item["child"]:
					self.assertTrue(item["icon"], f"{module}: {item['label']} has no icon")
