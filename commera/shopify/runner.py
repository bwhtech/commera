import frappe
from frappe import _
from frappe.utils import now_datetime

from commera.shopify.client import ShopifyClient
from commera.shopify.importers import IMPORTERS
from commera.shopify.importers.base import CREATED, SKIPPED, UPDATED, to_utc_iso
from commera.shopify.scan import StoreScanner

COUNT_FIELDS = {CREATED: "created_count", UPDATED: "updated_count", SKIPPED: "skipped_count"}


def execute_run(run_name: str) -> None:
	"""Background job entry. The import writes Items, Customers, stock and website settings, so it
	runs as Administrator. Only a user who may start a run can queue it."""
	frappe.set_user("Administrator")
	ImportRunner(frappe.get_doc("Shopify Import Run", run_name)).execute()


class ImportRunner:
	"""Runs one Shopify Import Run: a scan, or an import of the selected resources in order."""

	def __init__(self, run):
		self.run = run
		self.settings = frappe.get_single("Shopify Import Settings")
		self.client = ShopifyClient(self.settings)
		self.context = {}
		self.changed_since_utc = to_utc_iso(run.changed_since) if run.changed_since else None
		self.has_failures = False

	def execute(self) -> None:
		self.run.db_set({"status": "Running", "started_on": now_datetime()}, commit=True)
		try:
			if self.run.run_type == "Scan":
				self.run.db_set(
					"scan_report", frappe.as_json(StoreScanner(self.client, self.settings).scan())
				)
			else:
				for resource in IMPORTERS:
					if resource in self.run.resource_list:
						self.import_resource(resource)
				self.settings.db_set("last_import_started_on", self.run.started_on, update_modified=False)
			status = "Completed With Errors" if self.has_failures else "Completed"
			self.run.db_set({"status": status, "finished_on": now_datetime()}, commit=True)
		except Exception as error:
			frappe.db.rollback()
			frappe.log_error(f"Shopify import run {self.run.name} failed")
			self.run.db_set(
				{"status": "Failed", "error_message": str(error)[:1000], "finished_on": now_datetime()},
				commit=True,
			)

	def import_resource(self, resource: str) -> None:
		progress = self.run.get_progress_row(resource)
		progress.db_set("status", "Running", commit=True)
		try:
			importer = IMPORTERS[resource](self)
			records = importer.fetch_records()
		except Exception as error:
			frappe.db.rollback()
			self.has_failures = True
			self.run.add_issue(resource, _("Could not read from Shopify: {0}").format(error))
			progress.db_set("status", "Failed", commit=True)
			return

		progress.db_set("total", len(records), commit=True)
		for record in records:
			self.import_record(importer, progress, record)

		try:
			importer.finish()
			status = "Completed"
		except Exception as error:
			frappe.db.rollback()
			self.has_failures = True
			self.run.add_issue(resource, _("Could not finish: {0}").format(error))
			status = "Failed"
		progress.db_set("status", status, commit=True)

	def import_record(self, importer, progress, record: dict) -> None:
		# MariaDB refuses a savepoint name that starts with a digit.
		savepoint = f"shopify_{frappe.generate_hash(length=10)}"
		frappe.db.savepoint(savepoint)
		try:
			outcome = importer.import_record(record)
			fieldname = COUNT_FIELDS[outcome]
		except Exception as error:
			frappe.db.rollback(save_point=savepoint)
			if not isinstance(error, frappe.ValidationError):
				# A crash, not a refusal: keep the traceback for whoever fixes the importer.
				frappe.log_error(f"Shopify import of {record.get('id')} crashed")
			self.has_failures = True
			fieldname = "failed_count"
			self.run.add_issue(
				importer.resource, str(error), "Error", record.get("id"), importer.get_title(record)
			)

		# A message from one record must not show up as the message of the next one.
		frappe.clear_messages()
		progress.db_set(fieldname, (progress.get(fieldname) or 0) + 1)
		frappe.db.commit()
