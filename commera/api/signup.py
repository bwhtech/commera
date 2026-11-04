import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, cstr, validate_email_address

from commera.core import OTP_EXPIRY_SECONDS, get_otp_attempts_key, get_otp_key, send_otp

MAX_OTP_ATTEMPTS = 5


def verify_otp(email: str, otp: str, purpose: str | None = None):
	cache_key = get_otp_key(email, purpose)
	stored_otp = frappe.cache.get_value(cache_key)
	if stored_otp and cint(otp) == cint(stored_otp):
		frappe.cache.delete_value(cache_key)
		return

	if stored_otp and purpose:
		attempts_key = frappe.cache.make_key(get_otp_attempts_key(email, purpose))
		attempts = frappe.cache.incrby(attempts_key, 1)
		frappe.cache.expire(attempts_key, OTP_EXPIRY_SECONDS)
		if attempts >= MAX_OTP_ATTEMPTS:
			frappe.cache.delete_value(cache_key)
			frappe.throw(_("Too many wrong codes. Please ask for a new one."))
	frappe.throw(_("Invalid code") if purpose else _("Invalid OTP"))


def validate_user_names(first_name: str, last_name: str):
	if not cstr(first_name).strip():
		frappe.throw(_("Please enter your first name."))

	meta = frappe.get_meta("User")
	full_name = " ".join(name for name in (first_name, last_name) if name)
	for fieldname, value in (("first_name", first_name), ("last_name", last_name), ("full_name", full_name)):
		field = meta.get_field(fieldname)
		max_length = cint(field.length) or cint(frappe.db.type_map[field.fieldtype][1])
		if len(cstr(value)) > max_length:
			frappe.throw(_("{0} cannot be longer than {1} characters.").format(_(field.label), max_length))


def validate_single_email(email: str):
	# validate_email_address accepts "a@x.com, b@y.com" and "Name <a@x.com>" and returns the list unchanged;
	# either would mail the OTP to more than the one address typed.
	normalized_email = validate_email_address(email, throw=True)
	if "," in normalized_email or normalized_email != cstr(email).strip():
		frappe.throw(_("Please enter a single valid email address."), frappe.InvalidEmailAddressError)


# Pre-login by definition; writes nothing but the cached OTP, and is rate limited.
@frappe.whitelist(allow_guest=True)  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=30, seconds=60 * 60)
def send_signup_otp(email: str, first_name: str, last_name: str):
	validate_single_email(email)
	validate_user_names(first_name, last_name)
	user_exist = frappe.db.exists("User", {"email": email})
	if user_exist:
		frappe.throw(_("Email already in use."))
	send_otp(email)


# Pre-login by definition; writes nothing but the cached OTP, and is rate limited.
@frappe.whitelist(allow_guest=True)  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=30, seconds=60 * 60)
def send_login_otp(email: str):
	validate_single_email(email)
	user_exists = frappe.db.exists("User", email)
	if not user_exists:
		frappe.throw(_("Invalid login ID"))

	send_otp(email)


# Pre-login by definition; the OTP proves the caller owns the address.
@frappe.whitelist(allow_guest=True)  # nosemgrep: guest-whitelisted-method
# Keyed on the caller IP plus the email, so each address gets its own attempt budget per caller.
@rate_limit(key="email", limit=5, seconds=60 * 5)
def verify_signup_otp(email: str, first_name: str, last_name: str, otp: str):
	validate_user_names(first_name, last_name)
	verify_otp(email, otp)
	create_shopper_user(email, first_name, last_name)
	frappe.local.login_manager.login_as(email)


# Pre-login by definition; the OTP proves the caller owns the address.
@frappe.whitelist(allow_guest=True)  # nosemgrep: guest-whitelisted-method
@rate_limit(key="email", limit=5, seconds=60 * 5)
def verify_login_otp(email: str, otp: str):
	verify_otp(email, otp)
	frappe.local.login_manager.login_as(email)


def create_shopper_user(email: str, first_name: str, last_name: str | None = None) -> str:
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": first_name,
			"last_name": last_name,
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return user.name


def get_placeholder_first_name(email: str) -> str:
	return email.split("@", 1)[0]


# Pre-login by definition; writes nothing but the cached OTP, and is rate limited. It answers the same
# whether or not the email has an account, so checkout never tells a stranger who shops here.
@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=30, seconds=60 * 60)
def send_checkout_otp(email: str):
	email = cstr(email).strip().lower()
	validate_single_email(email)
	send_otp(email)


# Pre-login by definition; the OTP proves the caller owns the address.
@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(key="email", limit=5, seconds=60 * 5)
def verify_checkout_otp(email: str, otp: str):
	email = cstr(email).strip().lower()
	verify_otp(email, otp)

	enabled = frappe.db.get_value("User", email, "enabled")
	if enabled is None:
		create_shopper_user(email, get_placeholder_first_name(email))
	elif not enabled:
		frappe.throw(_("This account is disabled."), frappe.AuthenticationError)

	frappe.local.login_manager.login_as(email)
