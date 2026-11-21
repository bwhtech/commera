# Copyright (c) 2026, company@bwhstudios.com and Contributors

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.payments import COD_PAYMENT_MODE
from commera.localization.formatter import email_money
from commera.notifications import INVOICE_PRINT_FORMAT, seed_customer_emails, send_order_email
from commera.patches import set_commera_invoice_print_format
from commera.print_views import ORDER_PRINT_FORMAT, PACKING_SLIP_PRINT_FORMAT
from commera.tests.test_admin_orders import (
	COMPANY,
	credit_note_against_invoice,
	draft_delivery_note,
	invoice_against_order,
	make_shipping_rule,
	make_test_sales_order,
)

TAX_RATE = 6
SHIPPING_CHARGE = 49.0


def get_tax_account(label: str) -> str:
	abbr = frappe.get_cached_value("Company", COMPANY, "abbr")
	name = f"{label} - {abbr}"
	if not frappe.db.exists("Account", name):
		frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": label,
				"company": COMPANY,
				"parent_account": f"Current Liabilities - {abbr}",
				"account_type": "Tax",
			}
		).insert(ignore_permissions=True)
	return name


def make_taxed_order(payment_mode="ZZ Prepaid"):
	sales_order = make_test_sales_order(
		order_type="Shopping Cart", submit=False, shipping_rule=make_shipping_rule(SHIPPING_CHARGE).name
	)
	for label in ("ZZ CGST", "ZZ SGST"):
		sales_order.append(
			"taxes",
			{
				"charge_type": "On Net Total",
				"account_head": get_tax_account(label),
				"description": label,
				"rate": TAX_RATE,
			},
		)
	sales_order.save()
	sales_order.submit()
	sales_order.db_set({"custom_ecommerce_payment_mode": payment_mode, "contact_email": "pdfs@example.com"})
	return sales_order


def render(doctype: str, name: str, print_format: str) -> str:
	return frappe.get_print(doctype, name, print_format=print_format)


class TestPrintFormats(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.sales_order = make_taxed_order()

	def test_the_invoice_shows_its_number_lines_taxes_and_total(self):
		invoice = invoice_against_order(self.sales_order)

		html = render("Sales Invoice", invoice.name, INVOICE_PRINT_FORMAT)

		self.assertIn(invoice.name, html)
		self.assertIn(invoice.items[0].item_name, html)
		self.assertIn(f'ZZ CGST <span class="num">{TAX_RATE}%</span>', html)
		self.assertIn(email_money(invoice.rounded_total or invoice.grand_total, invoice.currency), html)
		self.assertIn(email_money(SHIPPING_CHARGE, invoice.currency), html)
		self.assertNotIn("Credit note", html)

	def test_a_return_invoice_prints_as_a_credit_note_against_its_invoice(self):
		invoice = invoice_against_order(self.sales_order)
		credit_note = credit_note_against_invoice(invoice)

		html = render("Sales Invoice", credit_note.name, INVOICE_PRINT_FORMAT)

		self.assertIn("Credit note number", html)
		self.assertIn(credit_note.name, html)
		self.assertIn(invoice.name, html)
		self.assertIn(email_money(abs(credit_note.grand_total), credit_note.currency), html)

	def test_the_packing_slip_lists_items_without_prices(self):
		delivery_note = draft_delivery_note(self.sales_order)

		html = render("Delivery Note", delivery_note.name, PACKING_SLIP_PRINT_FORMAT)

		self.assertIn(delivery_note.items[0].item_code, html)
		self.assertIn(self.sales_order.name, html)
		self.assertNotIn(email_money(delivery_note.items[0].rate, delivery_note.currency), html)
		self.assertNotIn(email_money(delivery_note.grand_total, delivery_note.currency), html)

	def test_the_order_confirmation_shows_the_order_and_its_total(self):
		html = render("Sales Order", self.sales_order.name, ORDER_PRINT_FORMAT)

		self.assertIn(self.sales_order.name, html)
		self.assertIn(self.sales_order.items[0].item_name, html)
		self.assertIn(email_money(self.sales_order.rounded_total, self.sales_order.currency), html)


class TestInvoicePrintFormatPatch(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)

	def test_only_a_site_still_on_standard_moves_to_the_commera_invoice(self):
		for current, expected in (
			("Standard", INVOICE_PRINT_FORMAT),
			(None, INVOICE_PRINT_FORMAT),
			("ZZ Own Format", "ZZ Own Format"),
		):
			with self.subTest(current=current):
				frappe.db.set_single_value("Commera Settings", "print_format", current)

				set_commera_invoice_print_format.execute()

				self.assertEqual(frappe.db.get_single_value("Commera Settings", "print_format"), expected)


class TestOrderConfirmationAttachment(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(setattr, frappe.flags, "mute_emails", frappe.flags.mute_emails)
		frappe.flags.mute_emails = True
		seed_customer_emails()
		frappe.db.set_single_value("Commera Settings", "print_format", None)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

	def get_attachments(self, sales_order) -> list[dict]:
		[attachments] = frappe.get_all(
			"Email Queue", filters={"reference_name": sales_order.name}, pluck="attachments"
		)
		return frappe.parse_json(attachments or "[]")

	def test_a_prepaid_confirmation_carries_the_invoice_pdf(self):
		sales_order = make_taxed_order()
		invoice = invoice_against_order(sales_order)

		send_order_email("order_confirmation", sales_order, ["pdfs@example.com"])

		[attachment] = self.get_attachments(sales_order)
		self.assertEqual(attachment["doctype"], "Sales Invoice")
		self.assertEqual(attachment["name"], invoice.name)
		self.assertEqual(attachment["print_format"], INVOICE_PRINT_FORMAT)

	def test_a_cash_on_delivery_confirmation_carries_nothing(self):
		sales_order = make_taxed_order(payment_mode=COD_PAYMENT_MODE)
		invoice_against_order(sales_order)

		send_order_email("order_confirmation", sales_order, ["pdfs@example.com"])

		self.assertEqual(self.get_attachments(sales_order), [])
