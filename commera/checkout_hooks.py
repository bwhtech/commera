import math
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils.data import cstr, flt

from commera.plugin_events import get_handlers

PLUGIN_FEE_FIELD = "commera_plugin_fee"


def get_cart_refusal(quotation) -> str | None:
	for handler in get_handlers("commera_checkout", "validate_cart"):
		with handle_hook_error("validate_cart", handler, quotation, strict=True):
			reason = frappe.get_attr(handler)(quotation)
			if reason and not isinstance(reason, str):
				raise TypeError(
					f'commera_checkout["validate_cart"] must return a str or None, got {reason!r}'
				)
		if reason:
			return reason
	return None


def apply_plugin_fees(quotation):
	"""Set quotation.flags.strict_plugin_fees at checkout: a failing fee hook then blocks it, while on a cart
	edit the fee is only left out, so a broken app never stops a shopper changing their cart."""
	# Imported here: commera.api.shipping imports this module.
	from commera.api.shipping import reindex_taxes

	handlers = get_handlers("commera_checkout", "cart_fees")
	if any(row.get(PLUGIN_FEE_FIELD) for row in quotation.taxes):
		# Dropped before the hooks run, so a fee priced on the grand total never compounds on its own last value.
		quotation.taxes = [row for row in quotation.taxes if not row.get(PLUGIN_FEE_FIELD)]
		reindex_taxes(quotation)
		quotation.calculate_taxes_and_totals()
	if not handlers:
		return

	for fee_row in get_plugin_fee_rows(quotation, handlers, strict=bool(quotation.flags.strict_plugin_fees)):
		quotation.append("taxes", fee_row)
	quotation.calculate_taxes_and_totals()


def get_plugin_fee_rows(quotation, handlers: list[str], strict: bool) -> list[dict]:
	precision = quotation.precision("tax_amount", "taxes")
	fee_rows = []
	for handler in handlers:
		with handle_hook_error("cart_fees", handler, quotation, strict):
			fees = frappe.get_attr(handler)(quotation) or []
			fee_rows += [fee_row for fee in fees if (fee_row := get_plugin_fee_row(fee, precision))]
	return fee_rows


def get_plugin_fee_row(fee: dict, precision: int) -> dict | None:
	description = cstr(fee.get("description")).strip()
	amount = fee.get("amount")
	if not is_finite_number(amount):
		raise ValueError(f"A cart fee amount must be a number, got {amount!r}")
	amount = flt(amount, precision)
	if amount == 0:
		return None
	if not description or amount < 0:
		raise ValueError(f"A cart fee needs a description and an amount above zero, got {fee!r}")

	return {
		"doctype": "Sales Taxes and Charges",
		"description": description,
		"charge_type": "Actual",
		"account_head": fee.get("account_head") or get_default_fee_account(),
		"tax_amount": amount,
		# ERPNext refuses an inclusive Actual charge, and a site default of 1 would fail checkout.
		"included_in_print_rate": 0,
		PLUGIN_FEE_FIELD: 1,
	}


def is_finite_number(amount) -> bool:
	return not isinstance(amount, bool) and isinstance(amount, int | float) and math.isfinite(amount)


def apply_delivery_option_hooks(quotation, options: list[dict], strict: bool) -> list[dict]:
	"""Each handler gets the options the previous one returned; a failing handler's answer is dropped."""
	precision = quotation.precision("tax_amount", "taxes")
	for handler in get_handlers("commera_checkout", "delivery_options"):
		with handle_hook_error("delivery_options", handler, quotation, strict):
			hooked_options = frappe.get_attr(handler)(quotation, [dict(option) for option in options])
			options = get_hooked_delivery_options(options, hooked_options, precision)
	return options


def get_hooked_delivery_options(options: list[dict], hooked_options, precision: int) -> list[dict]:
	if not isinstance(hooked_options, list) or not all(isinstance(option, dict) for option in hooked_options):
		raise TypeError(
			f'commera_checkout["delivery_options"] must return a list of dicts, got {hooked_options!r}'
		)

	hooked_by_title = {option.get("title"): option for option in hooked_options}
	titles = {option["title"] for option in options}
	if len(hooked_by_title) != len(hooked_options) or not set(hooked_by_title) <= titles:
		raise ValueError(
			f'commera_checkout["delivery_options"] may only drop or change offered options, got {hooked_options!r}'
		)

	return [
		get_hooked_delivery_option(option, hooked_by_title[option["title"]], precision)
		for option in options
		if option["title"] in hooked_by_title
	]


def get_hooked_delivery_option(option: dict, hooked_option: dict, precision: int) -> dict:
	option = dict(option)
	if "amount" in hooked_option:
		amount = hooked_option["amount"]
		if not is_finite_number(amount) or amount < 0:
			raise ValueError(f"A delivery option amount must be a number of zero or more, got {amount!r}")
		option["amount"] = flt(amount, precision)
	for field in ("label", "description"):
		if field in hooked_option:
			option[field] = cstr(hooked_option[field]).strip()
	option["is_free"] = not option["amount"]
	return option


def filter_payment_methods(quotation, methods: list[str], strict: bool) -> list[str]:
	for handler in get_handlers("commera_checkout", "payment_methods"):
		with handle_hook_error("payment_methods", handler, quotation, strict):
			kept_methods = frappe.get_attr(handler)(quotation, list(methods))
			if not isinstance(kept_methods, list) or not set(kept_methods) <= set(methods):
				raise ValueError(
					f'commera_checkout["payment_methods"] may only drop offered methods, got {kept_methods!r}'
				)
			methods = [method for method in methods if method in kept_methods]
	return methods


def get_default_fee_account() -> str:
	account = frappe.get_cached_value("Commera Settings", "Commera Settings", "charge_account_head")
	if not account:
		frappe.throw(_("Set a Charge Account Head in Commera Settings before a plugin charges a cart fee."))
	return account


@contextmanager
def handle_hook_error(key: str, handler: str, quotation, strict: bool):
	message_count = len(frappe.local.message_log)
	try:
		yield
	except Exception:
		frappe.log_error(
			title=f'commera_checkout["{key}"] hook failed: {handler}'[:140],
			reference_doctype="Quotation",
			reference_name=quotation.name,
			defer_insert=True,
		)
		# Whatever the app msgprinted is meant for its developer, never for the shopper.
		del frappe.local.message_log[message_count:]
		if strict:
			frappe.throw(_("Something went wrong, please try again."))
