# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import os

import frappe
from markupsafe import Markup

from commera.guest import is_guest

SETTINGS = "Commera Settings"
CACHE_KEY = "commera_storefront_plugins"
SLOTS = ("cart_banner", "checkout_banner", "page_overlay")
INCLUDE_TAGS = {"css": '<link rel="stylesheet" href="{0}">', "js": '<script defer src="{0}"></script>'}


def format_plugin_includes(kind: str) -> Markup:
	if is_checkout_request():
		return Markup()
	return Markup("\n").join(Markup(INCLUDE_TAGS[kind]).format(url) for url in get_storefront_plugins()[kind])


def plugin_slot(name: str) -> Markup:
	if name == "page_overlay" and is_checkout_request():
		return Markup()

	templates = get_storefront_plugins()["blocks"].get(name, [])
	if not templates:
		return Markup()

	html = []
	context = get_slot_context()
	for template in templates:
		try:
			html.append(frappe.get_template(template).render(context))
		except Exception:
			log_plugin_error(f"Storefront block {template} failed to render")
	return Markup("".join(html))


def get_slot_context() -> dict:
	return {
		"store_name": frappe.get_cached_value(SETTINGS, SETTINGS, "store_name"),
		"currency": frappe.get_cached_value("Global Defaults", "Global Defaults", "default_currency"),
		"language": frappe.local.lang,
		"is_guest": is_guest(),
	}


def is_checkout_request() -> bool:
	request = getattr(frappe.local, "request", None)
	return bool(request) and request.path.rstrip("/").endswith("/cart/checkout")


def get_storefront_plugins() -> dict:
	return frappe.cache.get_value(CACHE_KEY, generator=build_storefront_plugins)


def build_storefront_plugins() -> dict:
	plugins = {"css": [], "js": [], "blocks": {slot: [] for slot in SLOTS}}
	enabled_apps = get_enabled_storefront_apps(frappe.get_cached_doc(SETTINGS))
	for app in [app for app in frappe.get_installed_apps() if app in enabled_apps]:
		plugins["css"] += get_asset_urls(app, "commera_storefront_include_css")
		plugins["js"] += get_asset_urls(app, "commera_storefront_include_js")
		for slot, templates in frappe.get_hooks("commera_storefront_blocks", {}, app_name=app).items():
			if slot not in SLOTS:
				log_plugin_error(f"{app}: unknown storefront slot {slot}", f"Use one of: {', '.join(SLOTS)}.")
				continue
			plugins["blocks"][slot] += get_app_templates(app, templates)
	return plugins


def get_asset_urls(app: str, hook: str) -> list[str]:
	urls = []
	for url in frappe.get_hooks(hook, app_name=app):
		if not url.startswith(f"/assets/{app}/") or ".." in url:
			log_plugin_error(f"{app}: storefront include refused", f"{url} must start with /assets/{app}/.")
			continue
		urls.append(url)
	return urls


def get_app_templates(app: str, templates: list[str]) -> list[str]:
	valid_templates = []
	for template in templates:
		app_name, _, relative_path = template.partition("/")
		if (
			app_name != app
			or ".." in relative_path.split("/")
			or not os.path.isfile(frappe.get_app_path(app, relative_path))
		):
			log_plugin_error(
				f"{app}: storefront block refused", f"{template} must be a template file inside {app}."
			)
			continue
		valid_templates.append(template)
	return valid_templates


def get_enabled_storefront_apps(settings) -> set[str]:
	if not settings:
		return set()
	return {row.app for row in settings.storefront_apps if row.enabled}


def sync_storefront_apps(app_name: str | None = None):
	settings = frappe.get_single(SETTINGS)
	hooks = ("commera_storefront_include_css", "commera_storefront_include_js", "commera_storefront_blocks")
	declaring_apps = {
		app
		for app in frappe.get_installed_apps()
		if any(frappe.get_hooks(hook, None, app_name=app) for hook in hooks)
	}
	listed_apps = {row.app for row in settings.storefront_apps}

	for row in settings.storefront_apps:
		if row.app not in declaring_apps:
			frappe.db.delete("Commera Storefront App", {"name": row.name})
	for app in sorted(declaring_apps - listed_apps):
		settings.append("storefront_apps", {"app": app, "enabled": 0}).db_insert()

	frappe.clear_document_cache(SETTINGS, SETTINGS)
	clear_storefront_plugin_cache()


def clear_storefront_plugin_cache():
	frappe.cache.delete_value(CACHE_KEY)


def log_plugin_error(title: str, message: str | None = None):
	# Storefront pages are GET requests, which roll back: a plain insert would never reach Error Log.
	frappe.log_error(title=title, message=message, defer_insert=True)
