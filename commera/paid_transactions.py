"""Use accepted address text when ERPNext fills party details for paid placement."""

from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.selling.doctype.quotation.quotation import Quotation
from erpnext.selling.doctype.sales_order.sales_order import SalesOrder

from commera.paid_checkout import PaidAddressMixin


class PaidQuotation(PaidAddressMixin, Quotation):
	pass


class PaidSalesOrder(PaidAddressMixin, SalesOrder):
	pass


class PaidSalesInvoice(PaidAddressMixin, SalesInvoice):
	pass
