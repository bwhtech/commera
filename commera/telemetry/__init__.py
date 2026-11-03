"""Every event Commera sends to Pulse, with the properties `docs/telemetry.md` puts on all of them."""

from contextlib import contextmanager, suppress
from functools import wraps

import frappe
from frappe.utils import telemetry as frappe_telemetry
from frappe.utils import time_diff_in_seconds
from frappe.utils.data import now_datetime
from frappe.utils.telemetry import is_pulse_enabled, site_age

import commera
from commera.plugin_events import PLUGINS_USER

APP = "commera"
OTHER = "other"
SOURCE_FLAG = "commera_telemetry_source"
SOURCES = ("person", "demo_data", "import", "plugin")
INSTALL_MODULE = "Commera"
BUILT_IN_THEMES = ("Summer Theme", "Commera Starter", "Shop Default Theme", "Shop Base Theme")

ROWS_BUCKETS = ((10, "lt_10"), (100, "10_100"), (1000, "100_1000"))
VALUE_BUCKETS = (
	(100, "lt_100"),
	(1_000, "100_1k"),
	(10_000, "1k_10k"),
	(100_000, "10k_100k"),
	(1_000_000, "100k_1m"),
)
SHARE_BUCKETS = ((0.25, "lt_25"), (0.5, "25_50"), (0.75, "50_75"))
DURATION_BUCKETS = ((30, "lt_30s"), (60, "30_60s"), (120, "60_120s"))

# Most specific first: the first class an exception is an instance of names its kind.
ERROR_KINDS = (
	(frappe.MandatoryError, "mandatory"),
	(frappe.LinkValidationError, "link_validation"),
	(frappe.DuplicateEntryError, "duplicate_entry"),
	(frappe.PermissionError, "permission"),
	(frappe.QueryTimeoutError, "query_timeout"),
	(frappe.ValidationError, "validation"),
	(TimeoutError, "timeout"),
	(RuntimeError, "runtime"),
)


def default_properties() -> dict:
	return {"app_version": commera.__version__, "hosting": get_hosting()}


def get_hosting() -> str:
	if "commera_cloud" in frappe.get_installed_apps():
		return "commera_cloud"
	return "frappe_cloud" if frappe.conf.get("fc_team") else "self_hosted"


def get_boot_config() -> dict:
	"""The dashboard's boot key: whether to send anything at all, and the site's age for `pageview`."""
	if not is_pulse_enabled():
		return {"enabled": False}
	return {"enabled": True, "site_age": site_age()}


def capture(event: str, interval: str | None = None, **props):
	"""Send one event. Telemetry never fails the action it reports on."""
	with suppress(Exception):
		frappe_telemetry.capture(
			event,
			APP,
			properties={**default_properties(), **props},
			interval=interval,
		)


def telemetry_event(function):
	"""Run `function` only when telemetry is on, and never let it raise into the action it reports on."""

	@wraps(function)
	def wrapper(*args, **kwargs):
		if not is_pulse_enabled():
			return None
		with suppress(Exception):
			return function(*args, **kwargs)
		return None

	return wrapper


@contextmanager
def data_source(source: str):
	"""Mark what is made inside as demo data, an import or a plugin's, for the milestones it reaches."""
	previous = frappe.flags.get(SOURCE_FLAG)
	frappe.flags[SOURCE_FLAG] = source
	try:
		yield
	finally:
		frappe.flags[SOURCE_FLAG] = previous


def get_source() -> str:
	if source := frappe.flags.get(SOURCE_FLAG):
		return registry_value(source, SOURCES)
	return "plugin" if frappe.session.user == PLUGINS_USER else "person"


def registry_value(value, allowed) -> str:
	"""The value when the registry knows it, else `other`, so a custom name never leaks."""
	return value if value in allowed else OTHER


def theme_value(theme: str | None) -> str:
	"""A built-in theme by name, else `custom`: a merchant's own theme name never leaves the site."""
	return frappe.scrub(theme) if theme in BUILT_IN_THEMES else "custom"


def get_country_code(country: str | None) -> str | None:
	"""The ISO code of an ERPNext Country, which is named in full."""
	code = frappe.db.get_value("Country", country, "code") if country else None
	return code.upper() if code else None


def get_installed_at():
	"""When Commera was installed: its Module Def is made once, unlike the Installed Application row."""
	return frappe.db.get_value("Module Def", INSTALL_MODULE, "creation")


def seconds_since_install() -> float:
	installed_at = get_installed_at()
	return time_diff_in_seconds(now_datetime(), installed_at) if installed_at else 0


def days_since_install() -> int:
	return int(seconds_since_install() // 86400)


def bucket(value: float, limits, last: str) -> str:
	for limit, label in limits:
		if value < limit:
			return label
	return last


def rows_bucket(rows: int) -> str:
	return bucket(rows, ROWS_BUCKETS, "gt_1000")


def value_bucket(amount: float) -> str:
	"""Money as a band in the store currency, never as an amount."""
	return bucket(amount, VALUE_BUCKETS, "gt_1m")


def share_bucket(share: float) -> str:
	return bucket(share, SHARE_BUCKETS, "gt_75")


def duration_bucket(seconds: float) -> str:
	return bucket(seconds, DURATION_BUCKETS, "gt_120s")


def error_kind(exception: BaseException) -> str:
	"""An exception by class, never by message: a message can carry a store name or a credential."""
	return next(
		(kind for exception_class, kind in ERROR_KINDS if isinstance(exception, exception_class)), OTHER
	)
