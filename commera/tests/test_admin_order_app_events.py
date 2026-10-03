# Copyright (c) 2026, company@bwhstudios.com and Contributors

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from commera.api.admin.orders import get_order_app_events
from commera.tests.test_admin_orders import make_test_sales_order


def make_order_event(sales_order: str, event: str, deliveries: list, creation=None):
	commera_event = frappe.get_doc(
		{
			"doctype": "Commera Event",
			"event": event,
			"reference_doctype": "Sales Order",
			"reference_name": sales_order,
			"event_key": f"{sales_order}-{event}",
			"deliveries": deliveries,
		}
	).insert(ignore_permissions=True)
	if creation:
		frappe.db.set_value("Commera Event", commera_event.name, "creation", creation, update_modified=False)
	return commera_event


class TestOrderAppEvents(IntegrationTestCase):
	def setUp(self):
		self.sales_order = make_test_sales_order(submit=False).name

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_lists_deliveries_newest_event_first_with_app_title(self):
		error_log = frappe.log_error(title="ZZ app hook failed")
		make_order_event(
			self.sales_order,
			"order_placed",
			[
				{"app": "frappe", "handler": "frappe.placed_one", "status": "Done", "attempts": 1},
				{
					"app": "uninstalled_app",
					"handler": "uninstalled_app.placed_two",
					"status": "Failed",
					"attempts": 6,
					"last_error": error_log.name,
				},
			],
			creation=add_to_date(now_datetime(), hours=-1),
		)
		make_order_event(
			self.sales_order,
			"order_paid",
			[{"app": "frappe", "handler": "frappe.paid", "status": "Queued", "attempts": 2}],
		)

		rows = get_order_app_events(self.sales_order)

		self.assertEqual(
			[(row.event, row.app, row.status, row.attempts) for row in rows],
			[
				("order_paid", "Frappe Framework", "Queued", 2),
				("order_placed", "Frappe Framework", "Done", 1),
				("order_placed", "uninstalled_app", "Failed", 6),
			],
		)
		self.assertEqual(rows[2].error_log, error_log.name)
		self.assertIsNone(rows[0].error_log)

	def test_order_without_events_returns_empty_list(self):
		self.assertEqual(get_order_app_events(self.sales_order), [])

	def test_user_without_order_access_is_refused(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_order_app_events(self.sales_order)
