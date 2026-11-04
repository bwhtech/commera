import frappe
from frappe import _
from frappe.utils.data import cstr

from commera.api.signup import create_shopper_user, validate_single_email, validate_user_names, verify_otp
from commera.core import send_otp
from commera.sdk.account import get_profile
from commera.sdk.types import CustomerProfile

__all__ = ["log_in", "log_out", "send_login_code", "send_signup_code", "sign_up"]

LOGIN = "login"
SIGNUP = "signup"


def send_login_code(email: str) -> None:
	email = get_clean_email(email)
	account = get_account(email)
	if account and account.enabled:
		send_otp(email, LOGIN)


def log_in(email: str, code: str) -> CustomerProfile:
	email = get_clean_email(email)
	verify_otp(email, code, LOGIN)
	account = get_account(email)
	if not account:
		frappe.throw(_("Invalid code"))
	return start_session(account)


def send_signup_code(email: str, first_name: str, last_name: str | None = None) -> None:
	email = get_clean_email(email)
	validate_user_names(first_name, last_name)
	send_otp(email, SIGNUP)


def sign_up(email: str, first_name: str, code: str, last_name: str | None = None) -> CustomerProfile:
	email = get_clean_email(email)
	validate_user_names(first_name, last_name)
	verify_otp(email, code, SIGNUP)
	account = get_account(email)
	if not account:
		try:
			create_shopper_user(email, cstr(first_name).strip(), cstr(last_name).strip())
		except frappe.DuplicateEntryError:
			frappe.throw(_("This email is already registered. Please log in."))
		account = frappe._dict(name=email, enabled=1)
	return start_session(account)


def log_out() -> None:
	frappe.local.login_manager.logout()


def get_clean_email(email: str) -> str:
	email = cstr(email).strip().lower()
	validate_single_email(email)
	return email


def get_account(email: str) -> frappe._dict | None:
	return frappe.db.get_value("User", {"email": email}, ["name", "enabled"], as_dict=True)


def start_session(account: frappe._dict) -> CustomerProfile:
	if not account.enabled:
		frappe.throw(_("This account is disabled."), frappe.AuthenticationError)
	frappe.local.login_manager.login_as(account.name)
	return get_profile()
