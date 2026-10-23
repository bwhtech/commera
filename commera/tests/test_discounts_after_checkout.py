import frappe
from frappe.utils.data import flt

from commera.api.payments import COD_PAYMENT_MODE, make_sales_invoice, place_order
from commera.discounts.codes import get_code_discount
from commera.tests.test_discount_codes import CAP_RATE, SHIRT_RATE, DiscountCodeTestCase

try:
	from erpnext.accounts.doctype.sales_invoice.mapper import make_sales_return
except ImportError:
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return


def keep_rows(doc, item_codes: tuple[str, ...]):
	"""Drop the other rows the way Desk does, which numbers the kept rows from 1 again."""
	doc.items = [row for row in doc.items if row.item_code in item_codes]
	for idx, row in enumerate(doc.items, start=1):
		row.idx = idx


class TestDiscountsAfterCheckout(DiscountCodeTestCase):
	def change_discount(self, code: str, **values):
		discount = get_code_discount(code)
		frappe.db.set_value("Commera Discount", discount, values)
		frappe.clear_document_cache("Commera Discount", discount)

	def create_invoice(self, sales_order, item_codes: tuple[str, ...] | None = None):
		sales_invoice = make_sales_invoice(sales_order.name)
		if item_codes:
			keep_rows(sales_invoice, item_codes)
		sales_invoice.insert(ignore_permissions=True)
		sales_invoice.submit()
		return sales_invoice

	def create_return(self, sales_invoice, item_codes: tuple[str, ...] | None = None):
		credit_note = make_sales_return(sales_invoice.name)
		if item_codes:
			keep_rows(credit_note, item_codes)
		credit_note.insert(ignore_permissions=True)
		credit_note.submit()
		return credit_note

	def place_and_submit(self, lines: dict[str, int], codes=()):
		sales_order = self.place_order(self.create_quotation(lines, codes))
		sales_order.submit()
		return sales_order

	def test_the_order_is_booked_at_the_total_checked_before_payment(self):
		code = self.create_code(percentage=10)
		quotation = self.create_quotation({self.shirt: 1}, (code,))
		self.change_discount(code, value=20)

		sales_order = place_order(frappe.get_doc("Quotation", quotation.name), COD_PAYMENT_MODE)

		self.assertEqual(quotation.net_total, 81)
		self.assertEqual(sales_order.net_total, 81)
		self.assertEqual(sales_order.custom_code_order_discount, 9)

	def test_an_invoice_keeps_the_order_amounts_when_the_discount_changes(self):
		product = self.create_code(percentage=10, item_codes=(self.shirt,), combines_with_order=1)
		order = self.create_code(amount=13, combines_with_product=1)
		sales_order = self.place_and_submit({self.shirt: 1, self.cap: 1}, (product, order))
		self.change_discount(product, value=50)
		self.change_discount(order, value=30)

		sales_invoice = self.create_invoice(sales_order)

		self.assertEqual(self.get_line(sales_invoice, self.shirt).rate, 81)
		self.assertEqual(sales_invoice.net_total, 81 + CAP_RATE - 13)

	def test_a_credit_note_keeps_the_invoice_rate_after_the_discount_is_lowered(self):
		code = self.create_code(percentage=10, item_codes=(self.shirt,))
		sales_invoice = self.create_invoice(self.place_and_submit({self.shirt: 2}, (code,)))
		self.change_discount(code, value=5)

		credit_note = self.create_return(sales_invoice)

		self.assertEqual(self.get_line(credit_note, self.shirt).rate, 81)
		self.assertEqual(credit_note.net_total, -162)

	def test_returning_the_free_buy_x_get_y_item_refunds_nothing(self):
		code = self.create_code(
			discount_type="Buy X Get Y",
			buy_value=2,
			get_quantity=1,
			targets=[
				{"role": "Buys", "target_type": "Item", "target": self.shirt},
				{"role": "Gets", "target_type": "Item", "target": self.cap},
			],
		)
		sales_invoice = self.create_invoice(self.place_and_submit({self.shirt: 2, self.cap: 1}, (code,)))
		self.assertEqual(self.get_line(sales_invoice, self.cap).rate, 0)

		credit_note = self.create_return(sales_invoice, (self.cap,))

		self.assertEqual((credit_note.net_total, credit_note.grand_total), (0, 0))

	def test_a_full_return_refunds_what_the_order_discount_left_to_pay(self):
		code = self.create_code(percentage=10)
		sales_invoice = self.create_invoice(self.place_and_submit({self.shirt: 1, self.cap: 1}, (code,)))
		self.assertEqual(sales_invoice.net_total, 117)

		credit_note = self.create_return(sales_invoice)

		self.assertEqual(credit_note.net_total, -117)
		self.assertEqual(credit_note.grand_total, -sales_invoice.grand_total)

	def test_a_partial_invoice_from_desk_keeps_the_line_discount_on_its_item(self):
		code = self.create_code(percentage=10, item_codes=(self.cap,))
		sales_order = self.place_and_submit({self.shirt: 1, self.cap: 1}, (code,))

		cap_invoice = self.create_invoice(sales_order, (self.cap,))
		shirt_invoice = self.create_invoice(sales_order, (self.shirt,))

		self.assertEqual(self.get_line(cap_invoice, self.cap).rate, 36)
		self.assertEqual(self.get_line(shirt_invoice, self.shirt).rate, SHIRT_RATE)
