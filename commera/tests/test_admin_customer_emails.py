# Copyright (c) 2026, company@bwhstudios.com and Contributors

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin import customer_emails
from commera.notifications import get_customer_email_setting, seed_customer_emails
from commera.roles import COMMERA_ADMIN
from commera.sdk import STORE_ORDER_TYPE
from commera.tests.test_admin_customers import make_customer, make_item, make_webshop_order


class TestAdminCustomerEmails(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(self.clear_settings_cache)
		self.addCleanup(frappe.set_user, frappe.session.user)
		self.addCleanup(setattr, frappe.flags, "mute_emails", frappe.flags.mute_emails)
		frappe.flags.mute_emails = True
		frappe.set_user("Administrator")
		seed_customer_emails()
		self.clear_settings_cache()

	def clear_settings_cache(self):
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

	def get_row(self, email: str) -> dict:
		return next(row for row in customer_emails.get_customer_emails() if row["email"] == email)

	def make_order(self):
		sales_order = make_webshop_order(make_customer(), make_item())
		sales_order.db_set("contact_email", "emails-preview@example.com")
		return sales_order

	def make_email_template(self) -> str:
		return (
			frappe.get_doc(
				{
					"doctype": "Email Template",
					"name": f"ZZ Screen {frappe.generate_hash(length=6)}",
					"subject": "Custom {{ order_number }}",
					"use_html": 1,
					"response_html": "<p>Custom for {{ first_name }}</p>",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def test_the_list_names_each_email_and_marks_the_always_on_ones(self):
		rows = {row["email"]: row for row in customer_emails.get_customer_emails()}

		self.assertEqual(rows["order_confirmation"]["label"], "Order confirmation")
		self.assertTrue(rows["order_confirmation"]["enabled"])
		self.assertFalse(rows["order_confirmation"]["always_on"])
		self.assertTrue(rows["sign_in_code"]["always_on"])
		self.assertTrue(rows["order_link"]["always_on"])

	def test_an_email_turns_off_and_on(self):
		row = customer_emails.set_email_enabled("order_cancelled", False)
		self.clear_settings_cache()

		self.assertFalse(row["enabled"])
		self.assertEqual(get_customer_email_setting("order_cancelled").enabled, 0)

		customer_emails.set_email_enabled("order_cancelled", True)
		self.clear_settings_cache()
		self.assertTrue(self.get_row("order_cancelled")["enabled"])

	def test_an_always_on_email_cannot_be_turned_off(self):
		for email in ("sign_in_code", "order_link"):
			with self.subTest(email=email):
				with self.assertRaises(frappe.ValidationError):
					customer_emails.set_email_enabled(email, False)
				self.clear_settings_cache()
				self.assertEqual(get_customer_email_setting(email).enabled, 1)

	def test_an_unknown_email_is_refused(self):
		with self.assertRaises(frappe.DoesNotExistError):
			customer_emails.set_email_enabled("no_such_email", False)

	def test_a_template_is_set_then_cleared(self):
		template = self.make_email_template()

		row = customer_emails.set_email_template("order_confirmation", template)
		self.clear_settings_cache()
		self.assertEqual(row["email_template"], template)
		self.assertEqual(get_customer_email_setting("order_confirmation").email_template, template)

		row = customer_emails.set_email_template("order_confirmation", None)
		self.clear_settings_cache()
		self.assertIsNone(row["email_template"])
		self.assertFalse(get_customer_email_setting("order_confirmation").email_template)

	def test_a_template_that_does_not_exist_is_refused(self):
		with self.assertRaises(frappe.LinkValidationError):
			customer_emails.set_email_template("order_confirmation", "ZZ No Such Template")

	def test_the_template_picker_finds_email_templates(self):
		template = self.make_email_template()

		options = customer_emails.get_email_template_options(template)

		self.assertEqual(options, [{"label": template, "value": template}])

	def test_an_order_email_previews_the_latest_store_order(self):
		sales_order = self.make_order()

		preview = customer_emails.get_email_preview("order_confirmation")

		self.assertFalse(preview["needs_order"])
		self.assertEqual(preview["subject"], f"Order {sales_order.name} confirmed")
		self.assertIn(sales_order.name, preview["html"])
		self.assertIn("<html", preview["html"])

	def test_the_preview_uses_the_chosen_template(self):
		sales_order = self.make_order()
		customer_emails.set_email_template("order_confirmation", self.make_email_template())
		self.clear_settings_cache()

		preview = customer_emails.get_email_preview("order_confirmation")

		self.assertEqual(preview["subject"], f"Custom {sales_order.name}")
		self.assertIn("Custom for", preview["html"])

	def test_an_order_email_asks_for_an_order_when_the_store_has_none(self):
		frappe.db.delete("Sales Order", {"order_type": STORE_ORDER_TYPE})

		preview = customer_emails.get_email_preview("order_cancelled")

		self.assertEqual(preview, {"subject": None, "html": None, "needs_order": True})
		with self.assertRaises(frappe.ValidationError):
			customer_emails.send_test_email("order_cancelled")

	def test_emails_without_an_order_preview_with_sample_values(self):
		frappe.db.delete("Sales Order", {"order_type": STORE_ORDER_TYPE})

		sign_in = customer_emails.get_email_preview("sign_in_code")
		back_in_stock = customer_emails.get_email_preview("back_in_stock")

		self.assertIn(customer_emails.SAMPLE_SIGN_IN_CODE, sign_in["html"])
		self.assertIn("sign-in code", sign_in["subject"])
		self.assertFalse(back_in_stock["needs_order"])
		self.assertIn("is back in stock", back_in_stock["subject"])

	def sign_in_as_store_manager(self) -> str:
		email = f"emails-owner-{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Owner", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		user.add_roles("System Manager", COMMERA_ADMIN)
		frappe.set_user(email)
		return email

	def get_queued_recipients(self, recipient: str) -> list[list[str]]:
		queues = frappe.get_all("Email Queue Recipient", filters={"recipient": recipient}, pluck="parent")
		return [
			frappe.get_all("Email Queue Recipient", filters={"parent": queue}, pluck="recipient")
			for queue in queues
		]

	def test_a_test_email_goes_to_the_current_user_only(self):
		sales_order = self.make_order()
		recipient = self.sign_in_as_store_manager()

		answer = customer_emails.send_test_email("order_confirmation")

		self.assertEqual(answer, {"recipient": recipient})
		self.assertEqual(self.get_queued_recipients(recipient), [[recipient]])
		self.assertEqual(
			frappe.get_all("Email Queue", filters={"reference_name": sales_order.name}, pluck="name"), []
		)

	def test_a_turned_off_email_still_sends_a_test(self):
		customer_emails.set_email_enabled("back_in_stock", False)
		self.clear_settings_cache()
		recipient = self.sign_in_as_store_manager()

		customer_emails.send_test_email("back_in_stock")

		self.assertEqual(self.get_queued_recipients(recipient), [[recipient]])
