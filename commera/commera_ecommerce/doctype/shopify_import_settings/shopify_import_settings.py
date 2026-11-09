# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import re

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr

AUTH_CLIENT_CREDENTIALS = "Client Credentials"
AUTH_ACCESS_TOKEN = "Access Token"
DEFAULT_API_VERSION = "2026-10"
# bulkOperation(id:), which the import polls, exists from 2026-01.
MINIMUM_API_VERSION = "2026-01"
TOKEN_REQUEST_TIMEOUT = 30
# Shopify says a client credentials token lasts 86399 seconds. Asking again a few minutes early
# keeps a long import from sending a token that expires in flight.
TOKEN_EXPIRY_MARGIN_SECONDS = 300
SHOP_DOMAIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")


class ShopifyImportSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		access_token: DF.Password | None
		add_collections_to_menu: DF.Check
		api_version: DF.Data | None
		auth_method: DF.Literal["Client Credentials", "Access Token"]
		client_id: DF.Data | None
		client_secret: DF.Password | None
		connected_on: DF.Datetime | None
		default_collection: DF.Link | None
		granted_scopes: DF.SmallText | None
		import_inventory: DF.Check
		last_import_started_on: DF.Datetime | None
		option_attribute: DF.Data | None
		page_option_names: DF.SmallText | None
		primary_domain: DF.Data | None
		publish_active_products: DF.Check
		shop_currency: DF.Data | None
		shop_domain: DF.Data | None
		shop_name: DF.Data | None
	# end: auto-generated types

	def validate(self):
		self.shop_domain = normalize_shop_domain(self.shop_domain)
		self.api_version = cstr(self.api_version).strip() or DEFAULT_API_VERSION
		if self.api_version < MINIMUM_API_VERSION:
			frappe.throw(_("Use Shopify API version {0} or later.").format(MINIMUM_API_VERSION))

	def on_update(self):
		if self.has_value_changed("shop_domain") or self.has_value_changed("client_id"):
			self.clear_cached_token()

	@property
	def is_configured(self) -> bool:
		if not self.shop_domain:
			return False
		if self.auth_method == AUTH_ACCESS_TOKEN:
			return bool(self.get_password("access_token", raise_exception=False))
		return bool(self.client_id and self.get_password("client_secret", raise_exception=False))

	@property
	def graphql_url(self) -> str:
		return f"https://{self.shop_domain}/admin/api/{self.api_version}/graphql.json"

	@property
	def page_option_name_keys(self) -> list[str]:
		return [line.strip().casefold() for line in cstr(self.page_option_names).splitlines() if line.strip()]

	@property
	def token_cache_key(self) -> str:
		return f"shopify_import_token:{self.shop_domain}:{self.client_id}"

	def get_access_token(self) -> str:
		if not self.is_configured:
			frappe.throw(_("Connect a Shopify store first."))
		if self.auth_method == AUTH_ACCESS_TOKEN:
			return self.get_password("access_token")

		token = frappe.cache.get_value(self.token_cache_key)
		if token:
			return token

		token_data = self.request_client_credentials_token()
		expires_in = cint(token_data.get("expires_in")) or 86399
		frappe.cache.set_value(
			self.token_cache_key,
			token_data["access_token"],
			expires_in_sec=max(expires_in - TOKEN_EXPIRY_MARGIN_SECONDS, 60),
		)
		if token_data.get("scope"):
			self.db_set("granted_scopes", token_data["scope"], update_modified=False)
		return token_data["access_token"]

	def request_client_credentials_token(self) -> dict:
		"""Client credentials grant for a Dev Dashboard app installed on a store of the same organization."""
		response = requests.post(
			f"https://{self.shop_domain}/admin/oauth/access_token",
			data={
				"grant_type": "client_credentials",
				"client_id": self.client_id,
				"client_secret": self.get_password("client_secret"),
			},
			timeout=TOKEN_REQUEST_TIMEOUT,
		)
		if not response.ok:
			frappe.throw(
				_("Shopify refused the Client ID and Secret ({0}): {1}").format(
					response.status_code, get_error_text(response)
				)
			)

		token_data = response.json()
		if not token_data.get("access_token"):
			frappe.throw(_("Shopify answered without an access token."))
		return token_data

	def clear_cached_token(self):
		frappe.cache.delete_value(self.token_cache_key)


def normalize_shop_domain(value: str | None) -> str | None:
	"""Accept a pasted admin URL or a bare store handle, and keep only the myshopify.com host."""
	domain = cstr(value).strip().lower()
	if not domain:
		return None

	domain = re.sub(r"^https?://", "", domain).split("/")[0]
	if domain.startswith("admin.shopify.com"):
		frappe.throw(_("Enter the store's myshopify.com domain, not the admin URL."))
	if "." not in domain:
		domain = f"{domain}.myshopify.com"
	if not SHOP_DOMAIN_PATTERN.match(domain):
		frappe.throw(_("{0} is not a myshopify.com domain.").format(domain))
	return domain


def get_error_text(response) -> str:
	try:
		body = response.json()
	except ValueError:
		return cstr(response.text)[:300]
	return cstr(body.get("error_description") or body.get("errors") or body.get("error") or body)[:300]
