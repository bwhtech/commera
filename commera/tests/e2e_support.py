import os
from unittest.mock import patch

import frappe
from bwh_payments_core.connectors.razorpay.gateway import RazorpayGateway
from bwh_payments_core.connectors.razorpay.stub import StubRazorpayClient
from frappe.installer import update_site_config
from frappe.utils.password import update_password

from commera import install_summer_demo
from commera.api.payments import get_gateway_payment_request, open_checkout
from commera.core import _get_cart_quotation, get_otp_key
from commera.install import before_tests
from commera.roles import COMMERA_ADMIN

EMAIL_ACCOUNT = "E2E Outgoing"
MERCHANT_EMAIL = os.environ.get("COMMERA_MERCHANT_EMAIL", "merchant@e2e.commera.test")
MERCHANT_PASSWORD = os.environ.get("COMMERA_MERCHANT_PASSWORD", "admin")


def seed():
	validate_allow_tests()
	before_tests()
	with patch.object(install_summer_demo, "seed_storefront_analytics"):
		install_summer_demo.install_summer_demo()

	save_outgoing_email_account()
	update_site_config("mute_emails", 1)
	save_store_switches()
	save_merchant_user()
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- bench execute does not commit
	print("E2E_SEED_OK")


def get_signup_code(email: str, purpose: str | None = None) -> int | None:
	validate_allow_tests()
	return frappe.cache.get_value(get_otp_key(email, purpose))


def mark_payment_paid(reference_id: str) -> str:
	validate_allow_tests()
	payment_request = get_gateway_payment_request(reference_id)
	if not payment_request:
		frappe.throw(f"No Gateway Payment Request for {reference_id}")

	payment_request.status = "Paid"
	payment_request.save(ignore_permissions=True)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- bench execute does not commit
	return frappe.db.get_value("Gateway Payment Request", payment_request.name, "ref_docname")


def open_online_checkout(
	email: str, payment_mode: str, delivery_option: str | None = None, expected_total: float | None = None
) -> dict:
	validate_allow_tests()
	frappe.set_user(email)
	quotation = _get_cart_quotation()
	with patch.object(RazorpayGateway, "get_client", lambda self: StubRazorpayClient()):
		checkout = open_checkout(quotation, payment_mode, delivery_option, expected_total)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- bench execute does not commit
	reference_id = frappe.db.get_value(
		"Gateway Payment Request", {"ref_docname": quotation.name}, "name", order_by="creation desc"
	)
	return {"order_url": checkout["order_url"], "reference_id": reference_id}


def validate_allow_tests():
	if not frappe.conf.allow_tests:
		frappe.throw("Set allow_tests in site_config.json before running e2e helpers on this site.")


def save_outgoing_email_account():
	if frappe.db.exists("Email Account", EMAIL_ACCOUNT):
		return

	email_account = frappe.new_doc("Email Account")
	email_account.email_account_name = EMAIL_ACCOUNT
	email_account.email_id = "store@e2e.commera.test"
	email_account.smtp_server = "smtp.e2e.invalid"
	email_account.no_smtp_authentication = 1
	email_account.enable_outgoing = 1
	email_account.default_outgoing = 1
	email_account.insert(ignore_permissions=True)


def save_store_switches():
	frappe.db.set_single_value(
		"Commera Settings",
		{"allow_guest_checkout": 1, "cod_enabled": 1, "onboarding_completed": 1},
	)


def save_merchant_user():
	if frappe.db.exists("User", MERCHANT_EMAIL):
		user = frappe.get_doc("User", MERCHANT_EMAIL)
	else:
		user = frappe.new_doc("User")
		user.email = MERCHANT_EMAIL
		user.first_name = "E2E Merchant"
		user.send_welcome_email = 0
		user.insert(ignore_permissions=True)

	user.add_roles(COMMERA_ADMIN)
	update_password(MERCHANT_EMAIL, MERCHANT_PASSWORD)
