from typing import ClassVar
from zoneinfo import ZoneInfo

from frappe.utils import get_datetime, get_system_timezone

from commera.shopify.client import ShopifyApiError
from commera.shopify.queries import build_query

CREATED = "created"
UPDATED = "updated"
SKIPPED = "skipped"


class ResourceImporter:
	"""Reads one Shopify resource and writes each record into Commera. The runner owns the loop,
	the savepoints and the counts. A subclass only maps one record."""

	resource = ""
	queries: ClassVar[list[str]] = []
	supports_changed_filter = True

	def __init__(self, runner):
		self.runner = runner
		self.client = runner.client
		self.settings = runner.settings
		self.context = runner.context

	def fetch_records(self) -> list[dict]:
		changed_since = self.runner.changed_since_utc if self.supports_changed_filter else None
		return fetch_with_fallback(self.client, self.queries, changed_since)

	def import_record(self, record: dict) -> str:
		raise NotImplementedError

	def finish(self) -> None:
		"""Work that needs every record of the resource, after the loop."""

	def get_title(self, record: dict) -> str:
		return record.get("title") or record.get("displayName") or record.get("handle") or record.get("id")

	def warn(self, record: dict, message: str) -> None:
		self.runner.run.add_issue(self.resource, message, "Warning", record.get("id"), self.get_title(record))

	def is_unchanged(self, link, record: dict) -> bool:
		updated_at = to_system_datetime(record.get("updatedAt"))
		return bool(
			updated_at and link.shopify_updated_at and get_datetime(link.shopify_updated_at) >= updated_at
		)


def fetch_with_fallback(client, queries: list[str], changed_since_utc: str | None = None) -> list[dict]:
	"""Run the first query the configured API version accepts. A query that names a field this version
	does not have fails before any data is read, so the next, older query is tried."""
	schema_error = None
	for template in queries:
		try:
			return list(client.iter_bulk_records(build_query(template, changed_since_utc)))
		except ShopifyApiError as error:
			if not is_schema_error(error):
				raise
			schema_error = error
	raise schema_error


def is_schema_error(error: Exception) -> bool:
	message = str(error)
	return "doesn't exist on type" in message or "doesn't accept argument" in message


def to_system_datetime(value: str | None):
	"""Shopify sends UTC ISO 8601. Frappe stores naive datetimes in the system time zone."""
	if not value:
		return None
	moment = get_datetime(value.replace("Z", "+00:00"))
	return moment.astimezone(ZoneInfo(get_system_timezone())).replace(tzinfo=None)


def to_utc_iso(value) -> str:
	moment = get_datetime(value).replace(tzinfo=ZoneInfo(get_system_timezone()))
	return moment.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
