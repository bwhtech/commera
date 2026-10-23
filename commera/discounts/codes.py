import secrets

import frappe
from frappe import _
from frappe.utils.data import cint, cstr

from commera.plugin_events import get_handlers, handle_hook_error

MAX_GENERATED_CODES = 5000
MAX_CODES_IN_REQUEST = 200
# Leaves room for the 8 random characters within a code's 64.
MAX_PREFIX_LENGTH = 56
# No 0/O or 1/I: a code read off a receipt must not be mistyped.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def normalize_code(code: str | None) -> str:
	return cstr(code).strip().upper()


def get_code_discount(code: str) -> str | None:
	return frappe.get_cached_value("Commera Discount Code", normalize_code(code), "discount")


def add_code(discount: str, code: str, is_generated: bool = False) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Commera Discount Code",
				"code": code,
				"discount": discount,
				"is_generated": is_generated,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def validate_code_count(count: int, prefix: str = ""):
	if not 0 < cint(count) <= MAX_GENERATED_CODES:
		frappe.throw(_("Generate between 1 and {0} codes at a time.").format(MAX_GENERATED_CODES))
	if len(normalize_code(prefix)) > MAX_PREFIX_LENGTH:
		frappe.throw(_("A code prefix holds at most {0} characters.").format(MAX_PREFIX_LENGTH))


def generate_codes(discount: str, count: int, prefix: str = "") -> list[str]:
	validate_code_count(count, prefix)
	count, prefix = cint(count), normalize_code(prefix)
	codes = []
	while len(codes) < count:
		batch = {
			prefix + "".join(secrets.choice(CODE_ALPHABET) for _index in range(8))
			for _row in range(count - len(codes))
		}
		taken = set(
			frappe.get_all("Commera Discount Code", filters={"name": ["in", list(batch)]}, pluck="name")
		)
		codes += [add_code(discount, code, is_generated=True) for code in batch - taken]
	return codes


def enqueue_codes(discount: str, count: int, prefix: str = "") -> int:
	"""Returns how many were made now; a large batch is made by a background job instead."""
	validate_code_count(count, prefix)
	if cint(count) <= MAX_CODES_IN_REQUEST:
		return len(generate_codes(discount, count, prefix))
	frappe.enqueue(
		generate_codes,
		queue="long",
		enqueue_after_commit=True,
		discount=discount,
		count=cint(count),
		prefix=prefix,
	)
	return 0


def get_discount_code_refusal(quotation, code: str) -> str | None:
	for handler in get_handlers("commera_hooks", "validate_discount_code"):
		reason = None
		with handle_hook_error(
			"validate_discount_code", handler, quotation, bool(quotation.flags.strict_plugin_fees)
		):
			reason = frappe.get_attr(handler)(quotation, code)
			if reason and not isinstance(reason, str):
				raise TypeError(
					f'commera_hooks["validate_discount_code"] must return a str or None, got {reason!r}'
				)
		if reason:
			return reason
	return None
