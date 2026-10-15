import hashlib
import json
import os
import re

import frappe
from frappe.utils.data import cstr

from commera.plugin_events import is_supported_app
from commera.plugins.places import ICONS, NAME_PATTERN, PLACES, RECORD_DOCTYPES, RECORDLESS_PLACES
from commera.sdk import API_VERSION

CACHE_KEY = "commera:plugins"
BANNER_PATTERN = re.compile(r"commera-plugin-api:\s*(\d+)")
ENTRY_FIELDS = tuple(dict.fromkeys(field for spec in PLACES.values() for field in spec["fields"]))
CLIENT_FIELDS = (
	"key",
	"app",
	"place",
	"name",
	"label",
	"icon",
	"keywords",
	"order",
	"sidebar",
	"doctype",
	"confirm",
	"module_url",
	"error",
)


def get_registry() -> dict:
	if frappe.conf.developer_mode:
		return get_plugin_entries()

	return frappe.cache.get_value(CACHE_KEY, generator=get_plugin_entries)


def clear_registry_cache():
	frappe.cache.delete_value(CACHE_KEY)


def get_visible_plugins(user: str) -> dict:
	registry = get_registry()
	entries = [
		entry
		for entry in registry["entries"]
		if has_required_access(entry, user)
		and (entry["place"] not in RECORDLESS_PLACES or passes_condition(entry))
	]
	return {
		"apps": {app: registry["apps"][app] for app in dict.fromkeys(entry["app"] for entry in entries)},
		"entries": [get_client_entry(entry) for entry in entries],
	}


def get_client_entry(entry: dict) -> dict:
	return {field: entry.get(field) for field in CLIENT_FIELDS} | {
		"has_condition": bool(entry["condition"]) and entry["place"] not in RECORDLESS_PLACES,
		"has_method": bool(entry["method"]),
	}


def resolve_record_plugins(place_prefix: str, name: str | int, user: str) -> list[str]:
	doctype = RECORD_DOCTYPES[place_prefix]
	return [
		entry["key"]
		for entry in get_registry()["entries"]
		if entry["place"].startswith(f"{place_prefix}/")
		and has_required_access(entry, user)
		and passes_condition(entry, doctype, name)
	]


def get_registry_entry(key: str) -> dict | None:
	return next((entry for entry in get_registry()["entries"] if entry["key"] == key), None)


def has_required_access(entry: dict, user: str) -> bool:
	return not entry["requires"] or bool(frappe.has_permission(entry["requires"], "read", user=user))


def passes_condition(entry: dict, *arguments) -> bool:
	if not entry["condition"]:
		return True
	try:
		return bool(frappe.get_attr(entry["condition"])(*arguments))
	except Exception:
		frappe.log_error(title=f"Commera plugin {entry['key']} condition failed")
		return False


def get_plugin_entries() -> dict:
	registry = {"apps": {}, "entries": [], "problems": []}
	for app in frappe.get_installed_apps():
		if app != "commera" and is_supported_app(app):
			add_plugin_entries(registry, app)
	return registry


def add_plugin_entries(registry: dict, app: str):
	path = get_asset_path(app, "manifest.json")
	if not os.path.isfile(path):
		return

	try:
		# nosemgrep: frappe-security-file-traversal  # path is inside the app's built assets
		with open(path) as manifest_file:
			manifest = json.load(manifest_file)
	except ValueError:
		manifest = None
	if not isinstance(manifest, dict) or not isinstance(manifest.get("entries"), list):
		add_problem(registry, app, "manifest.json", f"isn't valid. Run bench build --app {app}.")
		return

	registry["apps"][app] = {"title": get_app_title(app)}
	if icon_url := get_icon_url(app, manifest.get("icon")):
		registry["apps"][app]["icon_url"] = icon_url
	version_error = get_version_error(manifest)
	taken = set()
	for manifest_entry in manifest["entries"]:
		entry = get_entry(app, manifest_entry if isinstance(manifest_entry, dict) else {})
		if reason := get_invalid_reason(entry, taken):
			add_problem(registry, app, f"{entry['place']}/{entry['name']}", reason)
			continue
		taken.add(get_uniqueness_key(entry))
		registry["entries"].append(add_module_url(entry, version_error))


def add_problem(registry: dict, app: str, subject: str, reason: str):
	message = f"{subject}: {reason}"
	frappe.log_error(title=f"Commera plugin {app}:{subject} skipped", message=message)
	registry["problems"].append({"app": app, "message": message})


def get_app_title(app: str) -> str:
	titles = frappe.get_hooks("commera_plugin_title", app_name=app) or frappe.get_hooks(
		"app_title", app_name=app
	)
	return (titles or [app])[0]


def get_version_error(manifest: dict) -> str | None:
	if manifest.get("api_version") != API_VERSION:
		return (
			f"Built for Commera API {manifest.get('api_version')}, not {API_VERSION}. "
			"Rebuild it with the current @commera/plugin-kit."
		)


def get_entry(app: str, manifest_entry: dict) -> dict:
	place, name = cstr(manifest_entry.get("place")), cstr(manifest_entry.get("name"))
	place_fields = PLACES.get(place, {}).get("fields", ())
	entry = {field: manifest_entry.get(field) if field in place_fields else None for field in ENTRY_FIELDS}
	if place == "pages" and entry["sidebar"] is None:
		entry["sidebar"] = True
	return entry | {
		"key": f"{app}:{place}:{name}",
		"app": app,
		"place": place,
		"name": name,
		"module": manifest_entry.get("module"),
		"hash": manifest_entry.get("hash"),
	}


def get_uniqueness_key(entry: dict) -> str:
	return entry["place"] if PLACES[entry["place"]].get("single") else entry["key"]


def get_invalid_reason(entry: dict, taken: set) -> str | None:
	spec = PLACES.get(entry["place"])
	if not spec:
		return f"Place {entry['place']} isn't supported by this Commera."
	if not NAME_PATTERN.fullmatch(entry["name"]):
		return "The name must be 1-40 characters of a-z, 0-9 and -, starting with a letter or digit."
	if get_uniqueness_key(entry) in taken:
		return f"{entry['app']} already has an entry here."
	if missing := [field for field in spec["required"] if entry[field] in (None, "")]:
		return f"{', '.join(missing)} is required."
	if entry["icon"] and entry["icon"] not in ICONS:
		return f"Icon {entry['icon']} isn't in Commera's icon set."
	if entry["requires"] and not frappe.db.exists("DocType", entry["requires"]):
		return f"requires names DocType {entry['requires']}, which doesn't exist."
	if entry["doctype"] and not frappe.db.get_value("DocType", entry["doctype"], "issingle"):
		return f"doctype {entry['doctype']} isn't a Single DocType."
	return get_module_reason(entry, spec) or get_function_reason(entry)


def get_module_reason(entry: dict, spec: dict) -> str | None:
	module = entry["module"]
	if spec["module"] == "required" and not module:
		return "It has no built module."
	if spec["module"] == "none" and module:
		return f"{entry['place']} is declared by its plugin block alone; remove the template."
	if spec["module"] == "optional" and bool(module) == bool(entry["method"] or entry["doctype"]):
		return "It needs exactly one of a template or a declared method or doctype."
	if module and not is_contained_asset(module, ".js"):
		return f"Module {module} must be a .js file inside public/commera/."


def is_contained_asset(relative_path: str, extension: str) -> bool:
	return (
		isinstance(relative_path, str)
		and relative_path.endswith(extension)
		and os.path.normpath(relative_path) == relative_path
		and not relative_path.startswith(("/", ".."))
	)


def get_icon_url(app: str, icon: str | None) -> str | None:
	if not icon or not is_contained_asset(icon, ".svg"):
		return None
	path = get_asset_path(app, icon)
	if not os.path.isfile(path):
		return None
	# nosemgrep: frappe-security-file-traversal  # path is inside the app's built assets
	with open(path, "rb") as icon_file:
		digest = hashlib.sha256(icon_file.read()).hexdigest()[:8]
	return f"/assets/{app}/commera/{icon}?v={digest}"


def get_function_reason(entry: dict) -> str | None:
	app = entry["app"]
	if entry["condition"] and not get_app_function(app, entry["condition"]):
		return f"condition {entry['condition']} must name a function inside {app}."
	if entry["method"] and not get_whitelisted_method(app, entry["method"]):
		return f"method {entry['method']} must name a whitelisted function inside {app}."


def get_whitelisted_method(app: str, path: str):
	method = get_app_function(app, path)
	return method if method in frappe.whitelisted else None


def get_app_function(app: str, path: str):
	# Keeps an app from pointing a condition or method at frappe internals or another app.
	if not cstr(path).startswith(f"{app}."):
		return None
	try:
		return frappe.get_attr(path)
	except Exception:
		return None


def add_module_url(entry: dict, version_error: str | None) -> dict:
	if version_error:
		return entry | {"error": version_error}
	if not entry["module"]:
		return entry

	app, module = entry["app"], entry["module"]
	path = get_asset_path(app, module)
	if not os.path.isfile(path):
		return entry | {"error": f"{module} isn't built. Run bench build --app {app}."}

	# nosemgrep: frappe-security-file-traversal  # path is inside the app's built assets
	with open(path) as module_file:
		banner = BANNER_PATTERN.search(module_file.readline())
	if not banner:
		return entry | {"error": f"{module} wasn't built with @commera/plugin-kit."}
	if int(banner.group(1)) != API_VERSION:
		return entry | {"error": f"{module} is built for Commera API {banner.group(1)}, not {API_VERSION}."}

	return entry | {"module_url": f"/assets/{app}/commera/{module}?v={cstr(entry['hash'])}"}


def get_asset_path(app: str, relative_path: str) -> str:
	# The served copy, so a module built but never linked into sites/assets reads as not built.
	return os.path.join(frappe.local.sites_path, "assets", app, "commera", relative_path)
