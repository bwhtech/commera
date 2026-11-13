"""A translation CSV import: a small file in the request, a large one as a background job on the long
queue, as Data Import does. The dashboard has no socket open, so it polls the job's status."""

import frappe
from frappe import _
from frappe.utils.background_jobs import get_job_status
from rq.job import JobStatus

from commera.localization import exchange

# A row takes about 4.5 ms to import, so this many answer in about 2 s.
REQUEST_IMPORT_ROWS = 500
JOB_TIMEOUT = 30 * 60
STATUS_SECONDS = 24 * 60 * 60


def import_file(file, language: str) -> dict:
	"""The report of a small file. A large one is queued: {"queued": True, "job_id": ...}."""
	rows = exchange.read_rows(file.get_content())
	exchange_language = exchange.get_exchange_language(language)
	if len(rows) <= REQUEST_IMPORT_ROWS:
		return exchange.TranslationImport(rows, exchange_language).run().as_dict()
	return queue_import(file.name, exchange_language.code)


def queue_import(file_name: str, language: str) -> dict:
	job_id = f"commera-translation-import-{frappe.generate_hash(length=12)}"
	set_status(job_id, "queued")
	frappe.enqueue(
		run_import,
		queue="long",
		timeout=JOB_TIMEOUT,
		job_id=job_id,
		enqueue_after_commit=True,
		file_name=file_name,
		language=language,
		import_id=job_id,
	)
	return {"queued": True, "job_id": job_id}


def run_import(file_name: str, language: str, import_id: str):
	"""Background job, run as the user who uploaded the file."""
	content = frappe.get_doc("File", file_name).get_content()
	report = exchange.import_csv(content, language).as_dict()
	frappe.db.after_commit.add(lambda: set_status(import_id, "done", report=report))


def get_status(job_id: str) -> dict:
	"""{"status": queued, done or failed, "report": ..., "error": ...} of the user's own import."""
	status = frappe.cache.get_value(status_key(job_id))
	if not status or status["user"] != frappe.session.user:
		frappe.throw(_("No such import."), frappe.DoesNotExistError)
	if status["status"] == "queued" and get_job_status(job_id) not in (
		JobStatus.QUEUED,
		JobStatus.STARTED,
		JobStatus.DEFERRED,
		JobStatus.SCHEDULED,
	):
		# The worker died or the job was dropped: say so, so the merchant can import again.
		status.update(status="failed", error=_("The import stopped before it finished. Please try again."))
	return {key: status.get(key) for key in ("status", "report", "error")}


def set_status(job_id: str, status: str, report: dict | None = None, error: str | None = None):
	value = {"user": frappe.session.user, "status": status, "report": report, "error": error}
	frappe.cache.set_value(status_key(job_id), value, expires_in_sec=STATUS_SECONDS)


def status_key(job_id: str) -> str:
	return f"commera:translation_import:{job_id}"
