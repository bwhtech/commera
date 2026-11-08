import frappe

from commera.api.storefront import rate_limited_guest_api
from commera.sdk import auth
from commera.sdk.types import CustomerProfile


@rate_limited_guest_api("POST", limit=30, seconds=60 * 60)
def send_login_code(email: str) -> None:
	auth.send_login_code(email)


@rate_limited_guest_api("POST", key="email", limit=5, seconds=60 * 5)
def log_in(email: str, code: str) -> CustomerProfile:
	return auth.log_in(email, code)


@rate_limited_guest_api("POST", limit=30, seconds=60 * 60)
def send_signup_code(email: str, first_name: str, last_name: str | None = None) -> None:
	auth.send_signup_code(email, first_name, last_name)


@rate_limited_guest_api("POST", key="email", limit=5, seconds=60 * 5)
def sign_up(email: str, first_name: str, code: str, last_name: str | None = None) -> CustomerProfile:
	return auth.sign_up(email, first_name, code, last_name)


@rate_limited_guest_api("POST", limit=60, seconds=60)
def log_out() -> None:
	auth.log_out()
