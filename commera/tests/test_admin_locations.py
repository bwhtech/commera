# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

"""The dashboard Locations API: switching store pickup on and giving each warehouse its pickup address."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin.settings import (
	find_address_location,
	get_locations,
	save_pickup_address,
	save_store_pickup,
	save_warehouse_pickup,
)

PIN_GEOJSON = frappe.as_json(
	{
		"type": "FeatureCollection",
		"features": [
			{
				"type": "Feature",
				"properties": {},
				"geometry": {"type": "Point", "coordinates": [46.6753, 24.7136]},
			}
		],
	}
)


def find_warehouse(screen, name):
	return next((warehouse for warehouse in screen["warehouses"] if warehouse["name"] == name), None)


class TestAdminLocations(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.db.get_value(
			"Warehouse", frappe.get_cached_value("Commera Settings", None, "ecommerce_warehouse"), "company"
		)
		# A rolled-back Single stays in Redis and would leak the switch into later tests.
		self.addCleanup(frappe.clear_document_cache, "Commera Settings", "Commera Settings")

	def create_warehouse(self, **values) -> str:
		warehouse = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": f"ZZ Location {frappe.generate_hash(length=6)}",
				"company": self.company,
				**values,
			}
		)
		return warehouse.insert(ignore_permissions=True).name

	def address_values(self, **values) -> dict:
		return {
			"address_line1": "1 Pickup Street",
			"city": "Riyadh",
			"country": frappe.get_cached_value("Company", self.company, "country"),
			**values,
		}

	def test_lists_active_warehouses_only(self):
		active = self.create_warehouse()
		disabled = self.create_warehouse(disabled=1)

		screen = get_locations()

		self.assertIsNotNone(find_warehouse(screen, active))
		self.assertIsNone(find_warehouse(screen, disabled))

	def test_store_pickup_switch_is_saved(self):
		self.assertEqual(save_store_pickup(1)["store_pickup_enabled"], 1)
		self.assertEqual(save_store_pickup(0)["store_pickup_enabled"], 0)

	def test_warehouse_pickup_switch_is_saved(self):
		warehouse = self.create_warehouse()

		screen = save_warehouse_pickup(warehouse, 1)

		self.assertEqual(find_warehouse(screen, warehouse)["allow_pickup"], 1)
		self.assertEqual(frappe.db.get_value("Warehouse", warehouse, "custom_store_pickup"), 1)

	def test_pickup_address_is_a_shop_address_linked_to_the_warehouse(self):
		warehouse = self.create_warehouse(custom_store_pickup=1)

		screen = save_pickup_address(warehouse, self.address_values(custom_store_location=PIN_GEOJSON))

		address = frappe.get_doc("Address", find_warehouse(screen, warehouse)["address"]["name"])
		self.assertEqual(address.address_type, "Shop")
		self.assertEqual(
			[(link.link_doctype, link.link_name) for link in address.links], [("Warehouse", warehouse)]
		)
		self.assertEqual(frappe.parse_json(address.custom_store_location), frappe.parse_json(PIN_GEOJSON))

	def test_a_new_address_is_named_after_its_warehouse(self):
		warehouse = self.create_warehouse(custom_store_pickup=1)

		screen = save_pickup_address(warehouse, self.address_values())

		entry = find_warehouse(screen, warehouse)
		self.assertEqual(entry["address"]["address_title"], entry["warehouse_name"])

	def test_arabic_admin_creates_an_untranslated_pickup_address(self):
		self.assertEqual(frappe.session.user, "Administrator")
		self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
		frappe.local.lang = "ar"
		frappe.translate.clear_cache()
		self.addCleanup(frappe.translate.clear_cache)
		self.assertEqual(frappe._("Shop"), "تسوّق")
		warehouse = self.create_warehouse(custom_store_pickup=1)

		screen = save_pickup_address(warehouse, self.address_values())

		entry = find_warehouse(screen, warehouse)
		address = frappe.get_doc("Address", entry["address"]["name"])
		self.assertEqual(address.address_type, "Shop")
		self.assertTrue(address.name.startswith(f"{entry['warehouse_name']}-Shop-"))
		self.assertNotIn(frappe._("Shop"), address.name)
		updated = save_pickup_address(warehouse, self.address_values(city="Jeddah"))
		self.assertEqual(find_warehouse(updated, warehouse)["address"]["name"], address.name)

	def test_saving_again_edits_the_same_address(self):
		warehouse = self.create_warehouse(custom_store_pickup=1)
		first = find_warehouse(save_pickup_address(warehouse, self.address_values()), warehouse)["address"]

		second = find_warehouse(
			save_pickup_address(warehouse, self.address_values(city="Jeddah")), warehouse
		)["address"]

		self.assertEqual(second["name"], first["name"])
		self.assertEqual(second["city"], "Jeddah")
		self.assertEqual(
			frappe.db.count("Dynamic Link", {"link_doctype": "Warehouse", "link_name": warehouse}), 1
		)

	def test_a_pin_sent_as_parsed_geojson_is_stored_as_json(self):
		warehouse = self.create_warehouse(custom_store_pickup=1)

		screen = save_pickup_address(
			warehouse, self.address_values(custom_store_location=frappe.parse_json(PIN_GEOJSON))
		)

		stored = find_warehouse(screen, warehouse)["address"]["custom_store_location"]
		self.assertEqual(frappe.parse_json(stored), frappe.parse_json(PIN_GEOJSON))

	def test_address_lookup_failure_leaves_the_pin_to_the_owner(self):
		with patch("commera.api.admin.settings.make_get_request", side_effect=ConnectionError):
			self.assertEqual(find_address_location("1 Pickup Street, Riyadh"), [])

	def test_address_lookup_returns_every_match_in_order_with_leaflet_bounds(self):
		response = [
			{
				"lat": "24.7136",
				"lon": "46.6753",
				"display_name": "Pickup Street, Riyadh",
				"boundingbox": ["24.70", "24.72", "46.66", "46.68"],
			},
			{"lat": "21.4858", "lon": "39.1925", "display_name": "Pickup Street, Jeddah"},
		]
		with patch("commera.api.admin.settings.make_get_request", return_value=response):
			matches = find_address_location("Pickup Street")

		self.assertEqual(
			matches,
			[
				{
					"label": "Pickup Street, Riyadh",
					"latitude": 24.7136,
					"longitude": 46.6753,
					"bounds": [[24.70, 46.66], [24.72, 46.68]],
				},
				{"label": "Pickup Street, Jeddah", "latitude": 21.4858, "longitude": 39.1925, "bounds": None},
			],
		)

	def test_address_lookup_skips_a_match_without_coordinates(self):
		with patch("commera.api.admin.settings.make_get_request", return_value=[{"display_name": "Nowhere"}]):
			self.assertEqual(find_address_location("Nowhere"), [])
