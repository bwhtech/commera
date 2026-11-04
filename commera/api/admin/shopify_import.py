"""The Shopify import screen: connect a store, scan it, and import it in the background."""

import frappe
from frappe import _
from frappe.utils import cint, cstr

from commera.commera_ecommerce.doctype.shopify_import_run.shopify_import_run import (
	RUN_TYPE_IMPORT,
	RUN_TYPE_SCAN,
	start_run,
)
from commera.commera_ecommerce.doctype.shopify_import_settings.shopify_import_settings import (
	AUTH_ACCESS_TOKEN,
	AUTH_CLIENT_CREDENTIALS,
)
from commera.shopify.client import ShopifyClient
from commera.shopify.importers import IMPORTERS
from commera.shopify.importers.store import save_shop_details
from commera.shopify.queries import SHOP_QUERY

SETTINGS_DOCTYPE = "Shopify Import Settings"
RUN_DOCTYPE = "Shopify Import Run"
OPTION_FIELDS = (
	"page_option_names",
	"option_attribute",
	"default_collection",
	"publish_active_products",
	"import_inventory",
	"add_collections_to_menu",
)
CHECK_FIELDS = ("publish_active_products", "import_inventory", "add_collections_to_menu")
RECENT_RUNS = 10
ISSUES_SHOWN = 200


@frappe.whitelist()
def get_shopify_import() -> dict:
	frappe.has_permission(SETTINGS_DOCTYPE, "read", throw=True)
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	return {
		"connection": {
			"shop_domain": settings.shop_domain,
			"auth_method": settings.auth_method,
			"client_id": settings.client_id,
			"has_client_secret": bool(settings.get_password("client_secret", raise_exception=False)),
			"has_access_token": bool(settings.get_password("access_token", raise_exception=False)),
			"api_version": settings.api_version,
			"is_configured": settings.is_configured,
			"shop_name": settings.shop_name,
			"shop_currency": settings.shop_currency,
			"primary_domain": settings.primary_domain,
			"granted_scopes": settings.granted_scopes,
			"connected_on": settings.connected_on,
		},
		"options": {fieldname: settings.get(fieldname) for fieldname in OPTION_FIELDS},
		"resources": list(IMPORTERS),
		"last_import_started_on": settings.last_import_started_on,
		"latest_scan": get_latest_scan_report(),
		"runs": frappe.get_all(
			RUN_DOCTYPE,
			fields=["name", "run_type", "status", "started_on", "finished_on", "creation"],
			order_by="creation desc",
			limit=RECENT_RUNS,
		),
	}


@frappe.whitelist(methods=["POST"])
def save_connection(
	shop_domain: str,
	auth_method: str = AUTH_CLIENT_CREDENTIALS,
	client_id: str | None = None,
	client_secret: str | None = None,
	access_token: str | None = None,
	api_version: str | None = None,
) -> dict:
	"""Save the store and its credentials, then call Shopify. A refused call rolls the save back."""
	frappe.has_permission(SETTINGS_DOCTYPE, "write", throw=True)
	if auth_method not in (AUTH_CLIENT_CREDENTIALS, AUTH_ACCESS_TOKEN):
		frappe.throw(_("Unknown authentication method {0}").format(auth_method))

	settings = frappe.get_single(SETTINGS_DOCTYPE)
	settings.shop_domain = shop_domain
	settings.auth_method = auth_method
	settings.client_id = cstr(client_id).strip() or settings.client_id
	settings.api_version = cstr(api_version).strip() or settings.api_version
	# A blank secret keeps the stored one, because the screen never receives it back.
	if cstr(client_secret).strip():
		settings.client_secret = cstr(client_secret).strip()
	if cstr(access_token).strip():
		settings.access_token = cstr(access_token).strip()
	settings.save()

	settings.clear_cached_token()
	save_shop_details(settings, ShopifyClient(settings).execute(SHOP_QUERY)["shop"])
	return get_shopify_import()


@frappe.whitelist(methods=["POST"])
def disconnect() -> dict:
	frappe.has_permission(SETTINGS_DOCTYPE, "write", throw=True)
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	settings.clear_cached_token()
	for fieldname in (
		"client_secret",
		"access_token",
		"shop_name",
		"shop_currency",
		"primary_domain",
		"granted_scopes",
		"connected_on",
	):
		settings.set(fieldname, None)
	settings.save()
	return get_shopify_import()


@frappe.whitelist(methods=["POST"])
def save_option(fieldname: str, value=None) -> dict:
	frappe.has_permission(SETTINGS_DOCTYPE, "write", throw=True)
	if fieldname not in OPTION_FIELDS:
		frappe.throw(_("{0} is not an import option").format(fieldname))

	settings = frappe.get_single(SETTINGS_DOCTYPE)
	settings.set(fieldname, cint(value) if fieldname in CHECK_FIELDS else value)
	settings.save()
	return {fieldname: settings.get(fieldname) for fieldname in OPTION_FIELDS}


@frappe.whitelist(methods=["POST"])
def start_scan() -> dict:
	frappe.has_permission(SETTINGS_DOCTYPE, "write", throw=True)
	check_is_configured()
	return {"name": start_run(RUN_TYPE_SCAN, []).name}


@frappe.whitelist(methods=["POST"])
def start_import(resources: list | str, only_changed: int | str = 0) -> dict:
	frappe.has_permission(SETTINGS_DOCTYPE, "write", throw=True)
	check_is_configured()

	resources = frappe.parse_json(resources) if isinstance(resources, str) else resources
	unknown = sorted(set(resources or []) - set(IMPORTERS))
	if unknown:
		frappe.throw(_("Unknown resources: {0}").format(", ".join(unknown)))
	if not resources:
		frappe.throw(_("Pick at least one thing to import."))

	changed_since = frappe.db.get_single_value(SETTINGS_DOCTYPE, "last_import_started_on")
	if cint(only_changed) and not changed_since:
		frappe.throw(_("Run a full import once before importing only the changes."))

	ordered = [resource for resource in IMPORTERS if resource in resources]
	return {"name": start_run(RUN_TYPE_IMPORT, ordered, bool(cint(only_changed)), changed_since).name}


@frappe.whitelist()
def get_run(name: str) -> dict:
	frappe.has_permission(SETTINGS_DOCTYPE, "read", throw=True)
	run = frappe.get_doc(RUN_DOCTYPE, name)
	return {
		"name": run.name,
		"run_type": run.run_type,
		"status": run.status,
		"only_changed": run.only_changed,
		"started_on": run.started_on,
		"finished_on": run.finished_on,
		"error_message": run.error_message,
		"progress": [
			{
				"resource": row.resource,
				"status": row.status,
				"total": row.total,
				"created": row.created_count,
				"updated": row.updated_count,
				"skipped": row.skipped_count,
				"failed": row.failed_count,
			}
			for row in run.resource_progress
		],
		"issues": [
			{
				"resource": row.resource,
				"level": row.level,
				"title": row.title,
				"message": row.message,
			}
			for row in run.issues[:ISSUES_SHOWN]
		],
		"issue_count": len(run.issues),
		"scan_report": frappe.parse_json(run.scan_report) if run.scan_report else None,
	}


def get_latest_scan_report() -> dict | None:
	report = frappe.db.get_value(
		RUN_DOCTYPE,
		{"run_type": RUN_TYPE_SCAN, "status": "Completed"},
		"scan_report",
		order_by="creation desc",
	)
	return frappe.parse_json(report) if report else None


def check_is_configured() -> None:
	if not frappe.get_single(SETTINGS_DOCTYPE).is_configured:
		frappe.throw(_("Connect a Shopify store first."))
