# Copyright (c) 2026, company@bwhstudios.com and Contributors
# Permission tests for the storefront order endpoints; Sales Order names are sequential and enumerable.

import importlib

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from commera.api.orders import (
	cancel_order,
	create_refund_payment_entry,
	get_sales_order_refund_status,
	make_refund_payment_entry,
	resolve_refund_amount,
)
from commera.api.signup import verify_otp
from commera.api.utils import ORDER_DETAIL_FIELDS, get_order_detail
from commera.tests.test_admin_orders import make_test_sales_order

LEAKED_FIELDS = ("contact_email", "contact_phone", "address_display", "customer")

# `return` is a keyword, so commera.api.return can only be reached by string path.
return_api = importlib.import_module("commera.api.return")


def make_website_user() -> str:
	"""Someone logged into the storefront who has no claim on the order under test."""
	email = f"zz-outsider-{frappe.generate_hash(length=8)}@example.com"
	frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "ZZ Outsider",
			"send_welcome_email": 0,
			"user_type": "Website User",
		}
	).insert(ignore_permissions=True)
	return email


class TestOrderAccess(IntegrationTestCase):
	def setUp(self):
		self.sales_order = make_test_sales_order()
		self.outsider = make_website_user()
		self.addCleanup(frappe.set_user, "Administrator")

	def test_order_detail_rejects_another_user(self):
		frappe.set_user(self.outsider)
		with self.assertRaises(frappe.PermissionError):
			get_order_detail(self.sales_order.name)

	def test_order_detail_rejects_guest(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_order_detail(self.sales_order.name)

	def test_order_detail_returns_only_allowlisted_fields(self):
		detail = get_order_detail(self.sales_order.name)["sales_order"]

		self.assertEqual(detail["name"], self.sales_order.name)
		self.assertEqual(set(detail) - {"items"}, set(ORDER_DETAIL_FIELDS))
		for fieldname in LEAKED_FIELDS:
			self.assertNotIn(fieldname, detail)

	def test_return_items_rejects_another_user(self):
		frappe.set_user(self.outsider)
		with self.assertRaises(frappe.PermissionError):
			return_api.return_items(self.sales_order.name, [{"item_code": "ZZ", "reason": "Damaged"}])

	def test_returned_items_rejects_another_user(self):
		frappe.set_user(self.outsider)
		with self.assertRaises(frappe.PermissionError):
			return_api.get_returned_items(self.sales_order.name)

	def test_refund_status_rejects_another_user(self):
		frappe.set_user(self.outsider)
		with self.assertRaises(frappe.PermissionError):
			get_sales_order_refund_status(self.sales_order.name)

	def test_refund_requires_write_permission_on_the_order(self):
		"""The refund endpoint is a staff action; owning the order is not enough to trigger a payout."""
		frappe.set_user(self.outsider)
		with self.assertRaises(frappe.PermissionError):
			create_refund_payment_entry(self.sales_order.name, amount=999999)

	def test_refund_rejects_the_owner_without_roles(self):
		"""Guards the fix itself: relaxing this to `read` would hand every shopper a payout button."""
		frappe.db.set_value("Sales Order", self.sales_order.name, "owner", self.outsider)
		frappe.set_user(self.outsider)
		with self.assertRaises(frappe.PermissionError):
			create_refund_payment_entry(self.sales_order.name)


class TestShopperCancel(IntegrationTestCase):
	"""A shopper has no permission on Item, and submitting a draft order re-reads its items."""

	def setUp(self):
		self.shopper = make_website_user()
		self.addCleanup(frappe.set_user, "Administrator")

	def cancel_as_shopper(self, sales_order):
		frappe.db.set_value("Sales Order", sales_order.name, "owner", self.shopper)
		frappe.set_user(self.shopper)
		cancel_order(sales_order.name)
		frappe.set_user("Administrator")
		return frappe.db.get_value("Sales Order", sales_order.name, "docstatus")

	def test_a_shopper_can_cancel_their_draft_order(self):
		self.assertEqual(self.cancel_as_shopper(make_test_sales_order(submit=False)), 2)

	def test_a_shopper_can_cancel_their_submitted_order(self):
		self.assertEqual(self.cancel_as_shopper(make_test_sales_order()), 2)

	def test_a_shopper_cannot_cancel_someone_elses_order(self):
		sales_order = make_test_sales_order(submit=False)
		frappe.set_user(self.shopper)
		with self.assertRaises(frappe.ValidationError):
			cancel_order(sales_order.name)


class TestRefundAmountClamp(UnitTestCase):
	"""The clamp is the only thing between a form post and the company bank account."""

	REFUNDABLE = 1000.0

	def test_none_refunds_the_outstanding_balance(self):
		self.assertEqual(resolve_refund_amount(self.REFUNDABLE, None), self.REFUNDABLE)

	def test_partial_amount_is_allowed(self):
		self.assertEqual(resolve_refund_amount(self.REFUNDABLE, 400), 400)

	def test_exact_balance_is_allowed(self):
		self.assertEqual(resolve_refund_amount(self.REFUNDABLE, 1000), 1000)

	def test_amount_above_the_balance_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			resolve_refund_amount(self.REFUNDABLE, 1000.01)

	def test_wildly_large_amount_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			resolve_refund_amount(self.REFUNDABLE, 999999)

	def test_negative_amount_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			resolve_refund_amount(self.REFUNDABLE, -5)

	def test_zero_is_rejected_rather_than_read_as_unspecified(self):
		for amount in (0, "0", 0.0):
			with self.subTest(amount=amount), self.assertRaises(frappe.ValidationError):
				resolve_refund_amount(self.REFUNDABLE, amount)

	def test_non_numeric_amount_does_not_become_a_full_refund(self):
		"""flt("abc") is 0.0, and `or` would have read that as "unspecified" and paid the maximum."""
		for amount in ("abc", "", "not-a-number"):
			with self.subTest(amount=amount), self.assertRaises(frappe.ValidationError):
				resolve_refund_amount(self.REFUNDABLE, amount)

	def test_a_partially_refunded_order_cannot_be_refunded_in_full_again(self):
		"""The cancel_order double-payout: after 400 of 1000 is refunded, 1000 must not go out again."""
		already_refunded = 400.0
		remaining = self.REFUNDABLE - already_refunded

		self.assertEqual(resolve_refund_amount(remaining, None), remaining)
		with self.assertRaises(frappe.ValidationError):
			resolve_refund_amount(remaining, self.REFUNDABLE)


class TestRefundEntryPoints(UnitTestCase):
	def test_internal_refund_helper_is_not_whitelisted(self):
		"""The whole split rests on this: only the permission-checked wrapper may be called remotely."""
		self.assertNotIn(
			"commera.api.orders.make_refund_payment_entry",
			{f"{method.__module__}.{method.__name__}" for method in frappe.whitelisted},
		)
		self.assertIn(
			"commera.api.orders.create_refund_payment_entry",
			{f"{method.__module__}.{method.__name__}" for method in frappe.whitelisted},
		)


class TestSignupOtp(UnitTestCase):
	def setUp(self):
		self.email = f"zz-otp-{frappe.generate_hash(length=8)}@example.com"
		self.addCleanup(frappe.cache.delete_value, f"otp:{self.email}")

	def test_otp_is_burned_after_one_use(self):
		frappe.cache.set_value(f"otp:{self.email}", 123456)

		verify_otp(self.email, "123456")

		with self.assertRaises(frappe.ValidationError):
			verify_otp(self.email, "123456")

	def test_wrong_otp_is_rejected(self):
		frappe.cache.set_value(f"otp:{self.email}", 123456)
		with self.assertRaises(frappe.ValidationError):
			verify_otp(self.email, "999999")

	def test_non_numeric_otp_is_rejected_cleanly(self):
		frappe.cache.set_value(f"otp:{self.email}", 123456)
		with self.assertRaises(frappe.ValidationError):
			verify_otp(self.email, "not-a-code")

	def test_missing_otp_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			verify_otp(self.email, "123456")
