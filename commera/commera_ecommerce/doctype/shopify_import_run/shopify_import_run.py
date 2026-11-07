# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr

RUN_TYPE_SCAN = "Scan"
RUN_TYPE_IMPORT = "Import"
ACTIVE_STATUSES = ("Queued", "Running")
# A store with thousands of broken records still gets a readable run. The rest are only counted.
MAX_ISSUES = 500
JOB_TIMEOUT_SECONDS = 6 * 60 * 60


class ShopifyImportRun(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from commera.commera_ecommerce.doctype.shopify_import_run_issue.shopify_import_run_issue import (
			ShopifyImportRunIssue,
		)
		from commera.commera_ecommerce.doctype.shopify_import_run_resource.shopify_import_run_resource import (
			ShopifyImportRunResource,
		)

		changed_since: DF.Datetime | None
		error_message: DF.SmallText | None
		finished_on: DF.Datetime | None
		issues: DF.Table[ShopifyImportRunIssue]
		only_changed: DF.Check
		resource_progress: DF.Table[ShopifyImportRunResource]
		resources: DF.SmallText | None
		run_type: DF.Literal["Scan", "Import"]
		scan_report: DF.JSON | None
		started_on: DF.Datetime | None
		status: DF.Literal["Queued", "Running", "Completed", "Completed With Errors", "Failed"]
	# end: auto-generated types

	def before_insert(self):
		active_run = frappe.db.get_value("Shopify Import Run", {"status": ("in", ACTIVE_STATUSES)})
		if active_run:
			frappe.throw(_("Another Shopify run is still going: {0}").format(active_run))

	@property
	def resource_list(self) -> list[str]:
		return [line.strip() for line in cstr(self.resources).splitlines() if line.strip()]

	def enqueue(self):
		frappe.enqueue(
			"commera.shopify.runner.execute_run",
			queue="long",
			timeout=JOB_TIMEOUT_SECONDS,
			enqueue_after_commit=True,
			run_name=self.name,
		)

	def get_progress_row(self, resource: str):
		return next(row for row in self.resource_progress if row.resource == resource)

	def add_issue(self, resource: str, message: str, level: str = "Error", shopify_id=None, title=None):
		"""Write straight to the table, so a long run shows its issues while it is still going."""
		count = frappe.db.count("Shopify Import Run Issue", {"parent": self.name})
		if count >= MAX_ISSUES:
			return

		issue = frappe.new_doc("Shopify Import Run Issue", parent_doc=self, parentfield="issues")
		issue.update(
			{
				"resource": resource,
				"level": level,
				"shopify_id": shopify_id,
				"title": cstr(title)[:140],
				"message": cstr(message)[:1000],
				"idx": count + 1,
			}
		)
		issue.db_insert()


def start_run(run_type: str, resources: list[str], only_changed: bool = False, changed_since=None):
	"""Insert a run with a progress row per resource, and queue it."""
	run = frappe.new_doc("Shopify Import Run")
	run.run_type = run_type
	run.resources = "\n".join(resources)
	run.only_changed = int(only_changed)
	run.changed_since = changed_since if only_changed else None
	for resource in resources:
		run.append("resource_progress", {"resource": resource, "status": "Pending"})
	run.insert(ignore_permissions=True)
	run.enqueue()
	return run
