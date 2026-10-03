# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.query_builder.functions import Count
from frappe.utils.data import cint

from commera.api.admin.orders import get_deliveries_query, query_deliveries
from commera.app_events import get_extension_apps
from commera.extensions.registry import get_app_title, get_registry


@frappe.whitelist()
def get_installed_apps() -> list[dict]:
	frappe.only_for("System Manager")

	registry = get_registry()
	failed_deliveries = get_failed_delivery_counts()
	return [
		{
			"app": app,
			"title": get_app_title(app),
			"icon_url": registry["apps"].get(app, {}).get("icon_url"),
			"version": getattr(frappe.get_module(app), "__version__", None),
			"extensions": [
				{field: entry.get(field) for field in ("place", "name", "label", "error")}
				for entry in registry["entries"]
				if entry["app"] == app
			],
			"problems": [problem["message"] for problem in registry["problems"] if problem["app"] == app],
			"failed_deliveries": failed_deliveries.get(app, 0),
		}
		for app in dict.fromkeys([*get_extension_apps(), *registry["apps"]])
	]


@frappe.whitelist()
def get_app_deliveries(app: str, status: str | None = None, start: int = 0, page_length: int = 20) -> dict:
	frappe.only_for("System Manager")

	delivery = frappe.qb.DocType("Commera Event Delivery")
	criterion = delivery.app == app
	if status:
		criterion &= delivery.status == status
	return {
		"rows": query_deliveries(criterion, cint(start), cint(page_length)),
		"total": get_deliveries_query(criterion).select(Count("*")).run()[0][0],
	}


def get_failed_delivery_counts() -> dict:
	delivery = frappe.qb.DocType("Commera Event Delivery")
	return dict(
		frappe.qb.from_(delivery)
		.select(delivery.app, Count("*"))
		.where(delivery.status == "Failed")
		.groupby(delivery.app)
		.run()
	)
