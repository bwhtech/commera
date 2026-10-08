# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import os

import frappe
from markupsafe import Markup, escape

from commera.guest import is_guest

SETTINGS = "Commera Settings"
CACHE_KEY = "commera_storefront_plugins"
SLOTS = ("cart_banner", "checkout_banner", "page_overlay")
INCLUDE_HOOKS = {
	"css": "commera_storefront_include_css",
	"js": "commera_storefront_include_js",
}
BLOCKS_HOOK = "commera_storefront_blocks"
HOOK_KEYS = (*INCLUDE_HOOKS.values(), BLOCKS_HOOK)


def format_plugin_styles() -> Markup:
	if is_checkout_request():
		return Markup()
	return Markup("\n").join(
		Markup('<link rel="stylesheet" href="{0}">').format(url) for url in get_storefront_plugins()["css"]
	)


def format_plugin_scripts() -> Markup:
	if is_checkout_request():
		return Markup()
	return Markup("\n").join(
		Markup('<script defer src="{0}"></script>').format(url) for url in get_storefront_plugins()["js"]
	)


def plugin_slot(name: str) -> Markup:
	if name == "page_overlay" and is_checkout_request():
		return Markup()

	html = []
	for template in get_storefront_plugins()["blocks"].get(name, []):
		try:
			html.append(frappe.get_template(template).render(get_slot_context()))
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
	installed_apps = frappe.get_installed_apps()
	for app in get_enabled_storefront_apps(frappe.get_cached_doc(SETTINGS)):
		if app not in installed_apps:
			continue
		for kind, hook in INCLUDE_HOOKS.items():
			plugins[kind] += get_asset_urls(app, hook)
		for slot, templates in get_app_hook(app, BLOCKS_HOOK, {}).items():
			if slot not in SLOTS:
				log_plugin_error(f"{app}: unknown storefront slot {slot}", f"Use one of: {', '.join(SLOTS)}.")
				continue
			plugins["blocks"][slot] += get_app_templates(app, templates)
	return plugins


def get_asset_urls(app: str, hook: str) -> list[str]:
	urls = []
	for url in get_app_hook(app, hook, []):
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


def get_app_hook(app: str, hook: str, default):
	return frappe.get_hooks(hook, default=default, app_name=app)


def get_enabled_storefront_apps(settings) -> set[str]:
	if not settings:
		return set()
	return {row.app for row in settings.storefront_apps if row.enabled}


def get_declaring_apps() -> list[str]:
	return [
		app for app in frappe.get_installed_apps() if any(get_app_hook(app, hook, None) for hook in HOOK_KEYS)
	]


def sync_storefront_apps(app_name: str | None = None):
	settings = frappe.get_single(SETTINGS)
	declaring_apps = get_declaring_apps()
	listed_apps = {row.app for row in settings.storefront_apps}

	for row in settings.storefront_apps:
		if row.app not in declaring_apps:
			frappe.db.delete("Commera Storefront App", {"name": row.name})
	for app in declaring_apps:
		if app not in listed_apps:
			settings.append("storefront_apps", {"app": app, "enabled": 0}).db_insert()

	frappe.clear_document_cache(SETTINGS, SETTINGS)
	clear_storefront_plugin_cache()


def clear_storefront_plugin_cache():
	frappe.cache.delete_value(CACHE_KEY)


def log_plugin_error(title: str, message: str | None = None):
	# Storefront pages are GET requests, which roll back: a plain insert would never reach Error Log.
	frappe.log_error(title=title, message=message, defer_insert=True)
