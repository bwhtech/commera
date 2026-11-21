# Copyright (c) 2026, company@bwhstudios.com and Contributors

from email import message_from_string
from email.header import decode_header, make_header
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, now_datetime

from commera import jobs
from commera.api.order_link import email_order_link
from commera.core import send_otp
from commera.notifications import (
	get_back_in_stock_context,
	get_customer_email_setting,
	seed_customer_emails,
	send_customer_email,
	validate_customer_emails,
)
from commera.patches import delete_default_email_templates
from commera.storefront_access import get_store_name
from commera.tests.test_admin_customers import make_customer, make_item, make_webshop_order

SHOPPER = "emails-shopper@example.com"


class TestCustomerEmails(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(self.clear_settings_cache)
		self.addCleanup(setattr, frappe.flags, "mute_emails", frappe.flags.mute_emails)
		frappe.flags.mute_emails = True
		seed_customer_emails()
		self.clear_settings_cache()

	def clear_settings_cache(self):
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

	def make_order(self, contact_email=SHOPPER, language=None):
		sales_order = make_webshop_order(make_customer(), make_item())
		sales_order.db_set({"contact_email": contact_email, "language": language})
		return sales_order

	def get_queued_emails(self, reference_name: str) -> list[dict]:
		queued = []
		for row in frappe.get_all(
			"Email Queue",
			filters={"reference_name": reference_name},
			fields=["name", "message", "show_as_cc"],
			order_by="creation",
		):
			mime = message_from_string(row.message)
			html = next(
				part.get_payload(decode=True).decode()
				for part in mime.walk()
				if part.get_content_type() == "text/html"
			)
			queued.append(
				{
					"recipients": frappe.get_all(
						"Email Queue Recipient", filters={"parent": row.name}, pluck="recipient"
					),
					"subject": str(make_header(decode_header(mime["Subject"]))),
					"cc": row.show_as_cc,
					"html": html,
				}
			)
		return queued

	def set_email_row(self, email: str, **values):
		row = get_customer_email_setting(email)
		frappe.db.set_value("Commera Email", row.name, values)
		self.clear_settings_cache()

	def test_the_confirmation_is_one_email_to_the_shopper_with_no_cc(self):
		sales_order = self.make_order()

		jobs.send_order_success_acknowledgement(sales_order, "after_insert")

		[email] = self.get_queued_emails(sales_order.name)
		self.assertEqual(email["recipients"], [SHOPPER])
		self.assertEqual(email["subject"], f"Order {sales_order.name} confirmed")
		self.assertFalse(email["cc"])
		self.assertIn("<!DOCTYPE html", email["html"])
		self.assertNotIn("email-body", email["html"], "Frappe's standard wrapper must not be applied")

	def test_an_arabic_order_gets_an_arabic_subject(self):
		frappe.get_doc(
			{
				"doctype": "Translation",
				"language": "ar",
				"source_text": "Order {order_number} confirmed",
				"translated_text": "تم تأكيد الطلب {order_number}",
			}
		).insert(ignore_permissions=True)
		sales_order = self.make_order(language="ar")

		jobs.send_order_success_acknowledgement(sales_order, "after_insert")

		[email] = self.get_queued_emails(sales_order.name)
		self.assertEqual(email["subject"], f"تم تأكيد الطلب {sales_order.name}")
		self.assertIn('dir="rtl"', email["html"])

	def test_a_turned_off_email_sends_nothing(self):
		self.set_email_row("order_confirmation", enabled=0)
		sales_order = self.make_order()

		jobs.send_order_success_acknowledgement(sales_order, "after_insert")

		self.assertEqual(self.get_queued_emails(sales_order.name), [])

	def test_an_email_template_replaces_the_file_until_it_is_cleared(self):
		template = frappe.get_doc(
			{
				"doctype": "Email Template",
				"name": f"ZZ Confirmation {frappe.generate_hash(length=6)}",
				"subject": "Custom {{ order_number }}",
				"use_html": 1,
				"response_html": "<p>Custom for {{ first_name }}</p>",
			}
		).insert(ignore_permissions=True)
		self.set_email_row("order_confirmation", email_template=template.name)
		sales_order = self.make_order()

		jobs.send_order_success_acknowledgement(sales_order, "after_insert")
		self.set_email_row("order_confirmation", email_template=None)
		jobs.send_order_success_acknowledgement(sales_order, "after_insert")

		custom, built_in = self.get_queued_emails(sales_order.name)
		self.assertEqual(custom["subject"], f"Custom {sales_order.name}")
		self.assertIn("Custom for", custom["html"])
		self.assertNotIn("email-body", custom["html"])
		self.assertEqual(built_in["subject"], f"Order {sales_order.name} confirmed")

	def test_sign_in_code_and_order_link_cannot_be_turned_off(self):
		settings = frappe.get_single("Commera Settings")
		for email in ("sign_in_code", "order_link"):
			with self.subTest(email=email):
				row = next(row for row in settings.customer_emails if row.email == email)
				row.enabled = 0
				with self.assertRaises(frappe.ValidationError):
					validate_customer_emails(settings)
				row.enabled = 1

	def test_cancellation_without_a_portal_user_goes_to_the_contact_email(self):
		sales_order = self.make_order()

		jobs.send_order_cancel_acknowledgement(sales_order, "on_cancel")

		[email] = self.get_queued_emails(sales_order.name)
		self.assertEqual(email["recipients"], [SHOPPER])
		self.assertEqual(email["subject"], f"Order {sales_order.name} is cancelled")
		self.assertFalse(email["cc"])

	def test_cancellation_with_no_email_at_all_sends_nothing(self):
		sales_order = self.make_order(contact_email=None)

		jobs.send_order_cancel_acknowledgement(sales_order, "on_cancel")

		self.assertEqual(self.get_queued_emails(sales_order.name), [])

	def test_the_order_link_email_carries_the_link(self):
		sales_order = self.make_order()

		email_order_link(sales_order.name, SHOPPER)

		[email] = self.get_queued_emails(sales_order.name)
		self.assertEqual(email["recipients"], [SHOPPER])
		self.assertEqual(email["subject"], f"Your link to order {sales_order.name}")
		key = frappe.db.get_value("Sales Order", sales_order.name, "custom_order_access_key")
		self.assertIn(key, email["html"])

	def test_back_in_stock_names_the_store(self):
		item_code = make_item()
		variant = frappe._dict(display_name="ZZ Restocked Jacket", route="zz-restocked-jacket")
		context = get_back_in_stock_context(item_code, variant)

		send_customer_email(
			"back_in_stock",
			[SHOPPER],
			{**context, "first_name": "Aisha", "product_url": "https://example.com/p"},
			reference=frappe._dict(doctype="Item", name=item_code),
		)

		[email] = self.get_queued_emails(item_code)
		self.assertEqual(email["subject"], "ZZ Restocked Jacket is back in stock")
		self.assertIn(frappe.utils.escape_html(get_store_name()), email["html"])

	def test_a_broken_custom_sign_in_code_falls_back_to_the_built_in_email(self):
		template = frappe.get_doc(
			{
				"doctype": "Email Template",
				"name": f"ZZ Broken Code {frappe.generate_hash(length=6)}",
				"subject": "Code",
				"use_html": 1,
				"response_html": "<p>{{ 1 / 0 }}</p>",
			}
		).insert(ignore_permissions=True)
		self.set_email_row("sign_in_code", email_template=template.name)

		with patch.dict(frappe.conf, {"developer_mode": 0}):
			send_otp(SHOPPER)

		parent = frappe.get_all(
			"Email Queue Recipient",
			filters={"recipient": SHOPPER},
			pluck="parent",
			order_by="creation desc",
			limit=1,
		)[0]
		message = frappe.db.get_value("Email Queue", parent, "message")
		self.assertIn(
			f"Your {get_store_name()} sign-in code",
			str(make_header(decode_header(message_from_string(message)["Subject"]))),
		)

	def test_the_sign_in_code_is_emailed(self):
		with patch.dict(frappe.conf, {"developer_mode": 0}):
			send_otp(SHOPPER)

		row = frappe.get_all(
			"Email Queue Recipient",
			filters={"recipient": SHOPPER},
			fields=["parent"],
			order_by="creation desc",
			limit=1,
		)
		message = frappe.db.get_value("Email Queue", row[0].parent, "message")
		self.assertIn(
			f"Your {get_store_name()} sign-in code",
			str(make_header(decode_header(message_from_string(message)["Subject"]))),
		)


class TestDeleteDefaultEmailTemplates(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)

	def ensure_template(self, name: str, modified):
		if not frappe.db.exists("Email Template", name):
			frappe.get_doc(
				{"doctype": "Email Template", "name": name, "subject": name, "response": name}
			).insert(ignore_permissions=True)
		frappe.db.set_value("Email Template", name, "modified", modified, update_modified=False)

	def test_only_the_untouched_shipped_templates_are_deleted(self):
		self.ensure_template("Order Confirmation", "2026-11-12 12:00:00")
		self.ensure_template("Item In Stock", add_days(now_datetime(), -1))

		delete_default_email_templates.execute()

		self.assertFalse(frappe.db.exists("Email Template", "Order Confirmation"))
		self.assertTrue(frappe.db.exists("Email Template", "Item In Stock"), "an edited template stays")
