import click
import frappe
from bwh_payments_core.contract import PaymentGatewayBase
from frappe.model.base_document import get_controller
from frappe.utils.caching import site_cache

from commera.plugins import providers as registry

KIND = "payment_connectors"
PROFILE_DOCTYPE = "Payment Gateway Profile"


def get_connector_doctypes() -> list[str]:
	return registry.get_provider_doctypes(KIND)


def get_connector_class(settings_doctype: str) -> type[PaymentGatewayBase]:
	return registry.get_provider_class(KIND, settings_doctype, PaymentGatewayBase)


@site_cache(ttl=60 * 60)
def get_available_payment_modes() -> list[str]:
	return frappe.get_all(PROFILE_DOCTYPE, filters={"enabled": 1}, pluck="name")


def clear_available_payment_modes():
	get_available_payment_modes.clear_cache()
	frappe.db.after_commit.add(get_available_payment_modes.clear_cache)
	frappe.db.after_rollback.add(get_available_payment_modes.clear_cache)


def resolve_payment_mode(payment_mode: str) -> str | None:
	requested = (payment_mode or "").strip().casefold()
	if not requested:
		return None
	for gateway in get_available_payment_modes():
		if gateway.casefold() == requested:
			return gateway
	return None


def validate_connectors(app_name: str | None = None):
	if problems := registry.get_provider_problems(KIND, PaymentGatewayBase):
		frappe.throw("<br>".join(problems), registry.ProviderNotRegisteredError)

	for doctype in get_unregistered_connectors():
		click.secho(
			f"{doctype} implements the payment gateway contract but is not in "
			f"commera_hooks[{KIND!r}], so Commera does not offer it.",
			fg="yellow",
		)


def get_unregistered_connectors() -> list[str]:
	registered = set(registry.get_declared_doctypes(KIND))
	return [
		doctype
		for doctype in frappe.get_all(
			"DocType", filters={"issingle": 1, "name": ["like", "% Gateway Settings"]}, pluck="name"
		)
		if doctype not in registered and implements_contract(doctype)
	]


def implements_contract(doctype: str) -> bool:
	try:
		return issubclass(get_controller(doctype), PaymentGatewayBase)
	except ImportError:
		return False
