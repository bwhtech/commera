# Copyright (c) 2026, company@bwhstudios.com and Contributors

import importlib.util
import unittest

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin.catalog import create_product
from commera.api.admin.discounts import save_discount
from commera.tests.test_admin_orders import ITEM_GROUP, make_test_sales_order

HAS_FLOW = importlib.util.find_spec("frappe.flow") is not None
if HAS_FLOW:
	from frappe.flow.doctype.flow_skill.flow_skill import sync_skills
	from frappe.flow.lib.tool import ToolContext
	from frappe.flow.tools.builtins import call_api

READ_APIS = (
	"commera.api.admin.catalog.get_products",
	"commera.api.admin.catalog.get_product",
	"commera.api.admin.catalog.get_top_products",
	"commera.api.admin.catalog.get_pricing_rows",
	"commera.api.admin.orders.get_orders",
	"commera.api.admin.orders.get_order",
	"commera.api.admin.orders.get_overview",
	"commera.api.admin.inventory.get_inventory",
	"commera.api.admin.inventory.get_stock_movements",
	"commera.api.admin.discounts.get_discounts",
	"commera.api.admin.discounts.get_discount",
	"commera.api.admin.analytics.get_revenue_report",
	"commera.api.admin.analytics.get_inventory_report",
	"commera.api.admin.analytics.get_storefront_report",
)
DETAIL_APIS = (
	"commera.api.admin.catalog.get_product",
	"commera.api.admin.orders.get_order",
	"commera.api.admin.discounts.get_discount",
)


@unittest.skipUnless(HAS_FLOW, "Frappe Flow is not installed")
class TestFlowSkill(IntegrationTestCase):
	def setUp(self):
		frappe.db.rollback()

	def tearDown(self):
		frappe.db.rollback()

	def test_the_skill_syncs_as_a_flow_skill(self):
		self.assertIn("commera/commera", sync_skills())
		self.assertEqual(frappe.db.get_value("Flow Skill", "commera/commera", "app"), "commera")

	def test_reads_run_without_approval_and_writes_still_ask(self):
		for path in READ_APIS:
			self.assertFalse(call_api.requires_confirmation({"method": path}), path)
		for path in (
			"commera.api.admin.catalog.create_product",
			"commera.api.admin.catalog.set_variant_price",
			"commera.api.admin.orders.fulfil_order",
		):
			self.assertTrue(call_api.requires_confirmation({"method": path}), path)

	def test_list_and_report_apis_run_in_a_read_only_transaction(self):
		ctx = ToolContext(session_id="test", agent="test", user=frappe.session.user, read_only=True)
		for path in READ_APIS:
			if path in DETAIL_APIS:
				continue
			with self.subTest(path):
				call_api(method=path, ctx=ctx)

	def test_detail_apis_never_write(self):
		item_template = create_product(
			title=f"ZZ Flow Product {frappe.generate_hash(length=6)}", collection=ITEM_GROUP, price=100
		)["name"]
		sales_order = make_test_sales_order().name
		discount = save_discount(
			{
				"method": "Code",
				"discount_type": "Amount Off Order",
				"value_type": "Percentage",
				"value": 10,
				"code": f"zz{frappe.generate_hash(length=6)}",
			}
		)["name"]
		args_by_path = {
			"commera.api.admin.catalog.get_product": {"item_template": item_template},
			"commera.api.admin.orders.get_order": {"sales_order": sales_order},
			"commera.api.admin.discounts.get_discount": {"name": discount},
		}
		self.assertEqual(set(args_by_path), set(DETAIL_APIS))

		for path, args in args_by_path.items():
			with self.subTest(path):
				writes_before = frappe.db.transaction_writes
				frappe.get_attr(path)(**args)
				self.assertEqual(frappe.db.transaction_writes, writes_before)
