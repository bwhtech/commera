import frappe
from frappe.rate_limiter import rate_limit

from commera.sdk import auth
from commera.sdk.types import CustomerProfile


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=30, seconds=60 * 60)
def send_login_code(email: str) -> None:
	auth.send_login_code(email)


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(key="email", limit=5, seconds=60 * 5)
def log_in(email: str, code: str) -> CustomerProfile:
	return auth.log_in(email, code)


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=30, seconds=60 * 60)
def send_signup_code(email: str, first_name: str, last_name: str | None = None) -> None:
	auth.send_signup_code(email, first_name, last_name)


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(key="email", limit=5, seconds=60 * 5)
def sign_up(email: str, first_name: str, code: str, last_name: str | None = None) -> CustomerProfile:
	return auth.sign_up(email, first_name, code, last_name)


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
def log_out() -> None:
	auth.log_out()
