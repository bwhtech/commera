"""A thin JSON client for a search server's REST API. Plain requests, so Commera needs no extra dependency."""

import frappe
import requests

# Reads sit on the storefront's request path, so a slow or absent server must fail fast.
READ_TIMEOUT = 3
WRITE_TIMEOUT = 30
# After a failed connection, report the server as down for this long instead of trying on every request.
DOWN_TTL = 30


class SearchServerError(Exception):
	pass


class SearchHttpClient:
	def __init__(self, url, headers):
		self.url = (url or "").rstrip("/")
		self.session = requests.Session()
		# Uncompressed answers: a gzip answer over about 1 KB arrives in pieces that wait ~40 ms for a
		# delayed TCP ack. Meilisearch facet and typeahead requests were about 10 times slower with gzip.
		self.session.headers["Accept-Encoding"] = "identity"
		self.session.headers.update(headers)

	def get(self, path, **params):
		return self.request("GET", path, params=params or None)

	def post(self, path, body, timeout=WRITE_TIMEOUT, **kwargs):
		return self.request("POST", path, json=body, timeout=timeout, **kwargs)

	def put(self, path, body):
		return self.request("PUT", path, json=body, timeout=WRITE_TIMEOUT)

	def patch(self, path, body):
		return self.request("PATCH", path, json=body, timeout=WRITE_TIMEOUT)

	def delete(self, path, **params):
		return self.request("DELETE", path, params=params or None, timeout=WRITE_TIMEOUT)

	def request(self, method, path, timeout=READ_TIMEOUT, **kwargs):
		"""The decoded JSON answer, or None for a 404."""
		response = self.send(method, path, timeout=timeout, **kwargs)
		if response is None:
			return None
		return response.json() if response.content else {}

	def send(self, method, path, timeout=READ_TIMEOUT, **kwargs):
		"""The raw response, or None for a 404."""
		try:
			response = self.session.request(method, f"{self.url}{path}", timeout=timeout, **kwargs)
		except requests.RequestException as error:
			frappe.cache.set_value(self.down_key, 1, expires_in_sec=DOWN_TTL)
			raise SearchServerError(f"The search server is unreachable at {self.url}: {error}") from error
		if response.status_code == 404:
			return None
		if not response.ok:
			raise SearchServerError(f"{method} {path} failed ({response.status_code}): {response.text}")
		return response

	def is_down(self):
		return bool(frappe.cache.get_value(self.down_key))

	@property
	def down_key(self):
		return f"commera_search_down:{self.url}"
