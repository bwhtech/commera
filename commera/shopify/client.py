import json
import time
from collections.abc import Iterator

import frappe
import requests
from frappe import _
from frappe.utils import cstr

from commera.shopify.bulk import assemble_bulk_records

REQUEST_TIMEOUT_SECONDS = 60
MAX_THROTTLE_RETRIES = 6
BULK_POLL_SECONDS = 3
BULK_TIMEOUT_SECONDS = 2 * 60 * 60

BULK_RUN_MUTATION = """
mutation runBulkQuery($query: String!) {
	bulkOperationRunQuery(query: $query) {
		bulkOperation { id status }
		userErrors { field message }
	}
}
"""

# bulkOperation(id:) is the status query from API version 2026-01. It replaced currentBulkOperation.
BULK_STATUS_QUERY = """
query bulkOperationStatus($id: ID!) {
	bulkOperation(id: $id) { id status errorCode objectCount url partialDataUrl }
}
"""

BULK_FINISHED_STATUSES = {"COMPLETED", "FAILED", "CANCELED", "EXPIRED"}


class ShopifyApiError(frappe.ValidationError):
	pass


class ShopifyClient:
	"""Calls to the GraphQL Admin API of the shop in Shopify Import Settings."""

	def __init__(self, settings=None):
		self.settings = settings or frappe.get_single("Shopify Import Settings")

	def execute(self, query: str, variables: dict | None = None) -> dict:
		for attempt in range(MAX_THROTTLE_RETRIES):
			response = requests.post(
				self.settings.graphql_url,
				json={"query": query, "variables": variables or {}},
				headers={"X-Shopify-Access-Token": self.settings.get_access_token()},
				timeout=REQUEST_TIMEOUT_SECONDS,
			)
			if response.status_code == 401:
				self.settings.clear_cached_token()
				raise ShopifyApiError(_("Shopify refused the access token. Connect the store again."))
			if response.status_code == 429 or (response.ok and is_throttled(response.json())):
				time.sleep(2**attempt)
				continue
			if not response.ok:
				raise ShopifyApiError(
					_("Shopify answered {0}: {1}").format(response.status_code, cstr(response.text)[:300])
				)

			body = response.json()
			if body.get("errors"):
				raise ShopifyApiError(format_errors(body["errors"]))
			return body.get("data") or {}

		raise ShopifyApiError(_("Shopify kept throttling the requests. Try again in a few minutes."))

	def iter_bulk_records(self, query: str) -> Iterator[dict]:
		"""Run one bulk export and yield its top-level records with their children attached."""
		url = self.run_bulk_query(query)
		if not url:
			return
		yield from assemble_bulk_records(self.iter_jsonl(url))

	def run_bulk_query(self, query: str) -> str | None:
		"""Return the JSONL file URL, or None when the query matched nothing."""
		result = self.execute(BULK_RUN_MUTATION, {"query": query})["bulkOperationRunQuery"]
		if result["userErrors"]:
			raise ShopifyApiError("; ".join(error["message"] for error in result["userErrors"]))

		operation_id = result["bulkOperation"]["id"]
		deadline = time.monotonic() + BULK_TIMEOUT_SECONDS
		while time.monotonic() < deadline:
			operation = self.execute(BULK_STATUS_QUERY, {"id": operation_id})["bulkOperation"]
			if operation["status"] in BULK_FINISHED_STATUSES:
				if operation["status"] != "COMPLETED":
					raise ShopifyApiError(
						_("Shopify bulk export ended as {0} ({1}).").format(
							operation["status"], operation.get("errorCode") or _("no error code")
						)
					)
				return operation.get("url")
			time.sleep(BULK_POLL_SECONDS)

		raise ShopifyApiError(_("The Shopify bulk export did not finish in time."))

	def iter_jsonl(self, url: str) -> Iterator[dict]:
		with requests.get(url, stream=True, timeout=REQUEST_TIMEOUT_SECONDS) as response:
			response.raise_for_status()
			for line in response.iter_lines(decode_unicode=True):
				if line:
					yield json.loads(line)


def is_throttled(body: dict) -> bool:
	return any(
		(error.get("extensions") or {}).get("code") == "THROTTLED" for error in body.get("errors") or []
	)


def format_errors(errors) -> str:
	if isinstance(errors, list):
		return "; ".join(cstr(error.get("message") or error) for error in errors)
	return cstr(errors)
