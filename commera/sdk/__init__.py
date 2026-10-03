import importlib
from contextlib import contextmanager

import frappe
from frappe import _

API_VERSION = 1
STORE_ORDER_TYPE = "Shopping Cart"
MODULES = ("cart", "catalog", "orders")

__all__ = ["API_VERSION", "STORE_ORDER_TYPE", "as_apps_user", *MODULES]


@contextmanager
def as_apps_user(app: str):
	"""Act as Commera's apps user, which holds every desk role, for a caller with no session of its own
	such as a guest webhook. The only way an app escalates through the SDK."""
	from commera.api.payments import system_user_session
	from commera.app_events import APPS_USER

	if app not in frappe.get_installed_apps():
		frappe.throw(_("{0} is not an installed app.").format(app), frappe.ValidationError)

	with system_user_session(APPS_USER):
		yield


def __getattr__(name: str):
	# Loaded on first use: commera.app_events imports this package, and every module here imports it back.
	if name in MODULES:
		return importlib.import_module(f"{__name__}.{name}")
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
