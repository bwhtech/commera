# Copyright (c) 2026, hussain@buildwithhussain.com and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.tests import test_payment_hooks as payment_hooks

STORE_WAREHOUSE = "Stores - LSD"


def enqueue_inline(method, enqueue_after_commit=False, **kwargs):
	"""Run the job in this process, and hold it for the commit when the caller asks for that."""
	if enqueue_after_commit:
		frappe.db.after_commit.add(lambda: method(**kwargs))
	else:
		method(**kwargs)


class TestBackInStockEmail(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		payment_hooks.TestPaymentHookIdempotency.ensure_fiscal_year()

	def setUp(self):
		frappe.db.set_single_value("Commera Settings", "ecommerce_warehouse", STORE_WAREHOUSE)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")
		self.addCleanup(frappe.clear_document_cache, "Commera Settings", "Commera Settings")

		self.notified_items = []
		for job_patch in (
			patch("commera.jobs.frappe.enqueue", side_effect=enqueue_inline),
			patch("commera.jobs.notify_users_if_item_in_stock", side_effect=self.notified_items.append),
		):
			job_patch.start()
			self.addCleanup(job_patch.stop)

	def create_stock_item(self):
		item_code = f"ZZ-RESTOCK-{frappe.generate_hash(length=8)}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": "ZZ Restock Item",
				"item_group": payment_hooks.ITEM_GROUP,
				"stock_uom": "Nos",
				"is_stock_item": 1,
			}
		).insert(ignore_permissions=True)
		return item_code

	def test_stock_entry_job_runs_after_the_stock_entry_commits(self):
		item_code = self.create_stock_item()
		# Nothing commits inside a test, so earlier tests' after-commit callbacks are still queued.
		frappe.db.after_commit.reset()

		stock_entry = frappe.new_doc("Stock Entry")
		stock_entry.update(
			{
				"stock_entry_type": "Material Receipt",
				"company": payment_hooks.COMPANY,
				"items": [
					{"item_code": item_code, "qty": 2, "t_warehouse": STORE_WAREHOUSE, "basic_rate": 10}
				],
			}
		)
		stock_entry.flags.ignore_permissions = True
		stock_entry.insert()
		stock_entry.submit()

		self.assertEqual(self.notified_items, [], "a worker cannot read the stock entry before commit")
		frappe.db.after_commit.run()
		self.assertEqual(self.notified_items, [item_code])
