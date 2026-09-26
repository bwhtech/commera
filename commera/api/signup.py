import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, cstr, validate_email_address

from commera.core import send_otp


def verify_otp(email: str, otp: str):
	"""Check the OTP and burn it, a code is single-use."""
	cache_key = f"otp:{email}"
	stored_otp = frappe.cache.get_value(cache_key)
	if not stored_otp or cint(otp) != cint(stored_otp):
		frappe.throw(_("Invalid OTP"))

	frappe.cache.delete_value(cache_key)


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

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": first_name,
			"last_name": last_name,
			"enabled": 1,
		}
	)
	user.insert(ignore_permissions=True)

	frappe.local.login_manager.login_as(email)


# Pre-login by definition; the OTP proves the caller owns the address.
@frappe.whitelist(allow_guest=True)  # nosemgrep: guest-whitelisted-method
@rate_limit(key="email", limit=5, seconds=60 * 5)
def verify_login_otp(email: str, otp: str):
	verify_otp(email, otp)
	frappe.local.login_manager.login_as(email)
