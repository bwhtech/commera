from collections.abc import Iterator
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.model.base_document import get_controller
from frappe.utils import scrub

from commera.plugin_events import is_supported_app


class ProviderNotRegisteredError(frappe.ValidationError):
	pass


def get_declared_doctypes(kind: str) -> list[str]:
	return list(dict.fromkeys(frappe.get_hooks("commera_hooks", {}).get(kind, [])))


def get_provider_doctypes(kind: str) -> list[str]:
	"""The settings DocTypes that apps declare in commera_hooks[kind], minus apps built for another API."""
	return [
		doctype
		for doctype in get_declared_doctypes(kind)
		if (app := get_doctype_app(doctype)) and is_supported_app(app)
	]


def get_doctype_app(doctype: str) -> str | None:
	module = frappe.db.get_value("DocType", doctype, "module", cache=True)
	return frappe.local.module_app.get(scrub(module)) if module else None


def get_provider_class(kind: str, doctype: str, base_class: type) -> type:
	if doctype not in get_provider_doctypes(kind):
		frappe.throw(
			_("{0} is not a registered provider").format(frappe.bold(doctype)), ProviderNotRegisteredError
		)

	controller = get_controller(doctype)
	if not issubclass(controller, base_class):
		frappe.throw(
			_("{0} does not subclass {1}").format(frappe.bold(doctype), base_class.__name__),
			ProviderNotRegisteredError,
		)
	return controller


def get_provider_problems(kind: str, base_class: type) -> list[str]:
	"""What is wrong with each declared provider, so migrate and app install can stop on it."""
	problems = []
	for doctype in get_declared_doctypes(kind):
		if not frappe.db.exists("DocType", doctype):
			problems.append(f"{doctype} is declared in commera_hooks[{kind!r}] but is not a DocType.")
		elif not frappe.get_meta(doctype).issingle:
			problems.append(f"{doctype} must be a Single DocType to be a provider.")
		elif not issubclass(get_controller(doctype), base_class):
			problems.append(f"{doctype} does not subclass {base_class.__module__}.{base_class.__name__}.")
	return problems


@contextmanager
def use_providers(kind: str, providers: dict[str, object]) -> Iterator[None]:
	"""Inside the block, only these providers exist, as these objects. Made for tests."""
	overrides = frappe.local.flags.setdefault("commera_provider_overrides", {})
	previous = overrides.get(kind)
	overrides[kind] = providers
	try:
		yield
	finally:
		if previous is None:
			overrides.pop(kind, None)
		else:
			overrides[kind] = previous


def get_provider_overrides(kind: str) -> dict[str, object] | None:
	return (frappe.local.flags.get("commera_provider_overrides") or {}).get(kind)
