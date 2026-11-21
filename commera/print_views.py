from functools import partial

import frappe
from frappe import _
from frappe.utils import flt, formatdate

from commera.api.shipping import get_charge_amount, get_charge_line_kind, get_shipping_rule_accounts
from commera.discounts.allocations import get_order_discount_rows
from commera.localization.formatter import email_money
from commera.notifications import (
	INVOICE_PRINT_FORMAT,
	get_brand_context,
	get_order_addresses,
	get_order_facts,
	get_order_items,
	get_order_totals,
)

PACKING_SLIP_PRINT_FORMAT = "Commera Packing Slip"
ORDER_PRINT_FORMAT = "Commera Order Confirmation"
PRINT_TEMPLATES = "commera/templates/print"


def set_default_invoice_print_format():
	if frappe.db.get_single_value("Commera Settings", "print_format") in (None, "", "Standard"):
		frappe.db.set_single_value("Commera Settings", "print_format", INVOICE_PRINT_FORMAT)


def get_commera_print_view(doc) -> dict:
	if doc.doctype == "Sales Invoice":
		view = get_credit_note_view(doc) if doc.is_return else get_invoice_view(doc)
		template = "credit_note" if doc.is_return else "tax_invoice"
	elif doc.doctype == "Delivery Note":
		view, template = get_packing_slip_view(doc), "packing_slip"
	else:
		view, template = get_order_confirmation_view(doc), "order_confirmation"
	return {
		"template": f"{PRINT_TEMPLATES}/{template}.html",
		"tokens": get_print_tokens(),
		"brand": get_print_brand(doc.company),
		"money": partial(email_money, currency=doc.currency),
		**view,
	}


def get_print_tokens() -> dict:
	return frappe.get_file_json(frappe.get_app_path("commera", "templates", "print", "tokens.json"))


def get_print_brand(company: str) -> dict:
	brand = get_brand_context(company)
	country = frappe.get_cached_value("Company", company, "country") if company else None
	return {**brand, "tax_id_label": "GSTIN" if country == "India" else _("Tax ID")}


def get_invoice_view(invoice) -> dict:
	sales_order = get_source_order(invoice, "sales_order")
	has_tax_id = bool(frappe.get_cached_value("Company", invoice.company, "tax_id"))
	outstanding = flt(invoice.outstanding_amount)
	return {
		"doc": {
			**get_invoice_document(invoice),
			"title": _("Tax invoice") if has_tax_id else _("Invoice"),
			"number_label": _("Tax invoice number") if has_tax_id else _("Invoice number"),
			"order_name": sales_order.name if sales_order else None,
			"transaction_date": formatdate(sales_order.transaction_date) if sales_order else None,
			"payment_method": sales_order.custom_ecommerce_payment_mode if sales_order else None,
			"payment_status": _("Paid in full")
			if outstanding <= 0
			else _("{0} due").format(email_money(outstanding, invoice.currency)),
		},
		"copy": {"closing": _("This invoice was issued electronically and is valid without a signature.")},
	}


def get_credit_note_view(credit_note) -> dict:
	sales_order = get_source_order(credit_note, "sales_order")
	return {
		"doc": {
			**get_invoice_document(credit_note),
			"title": _("Credit note"),
			"number_label": _("Credit note number"),
			"order_name": sales_order.name if sales_order else None,
			"return_against": credit_note.return_against,
			"return_against_date": formatdate(
				frappe.db.get_value("Sales Invoice", credit_note.return_against, "posting_date")
			)
			if credit_note.return_against
			else None,
			"refund_method": sales_order.custom_ecommerce_payment_mode if sales_order else None,
		},
		"copy": {
			"closing": _(
				"The credit is refunded to your original payment method. Questions? Write to us and we'll help."
			)
		},
	}


def get_invoice_document(invoice) -> dict:
	addresses = get_order_addresses(invoice)
	taxes, charges = get_invoice_taxes(invoice)
	total_taxes = sum(tax["amount"] for tax in taxes)
	taxes_included = bool(taxes) and all(tax["included"] for tax in taxes)
	return {
		"name": invoice.name,
		"posting_date": formatdate(invoice.posting_date),
		"billing": addresses["billing"] or addresses["shipping"],
		"shipping": addresses["shipping"] if addresses["billing"] else None,
		"customer_tax_id": invoice.tax_id,
		"lines": [
			{
				"item_name": row.item_name,
				"item_code": row.item_code,
				"gst_hsn_code": row.get("gst_hsn_code"),
				"qty": abs(flt(row.qty)),
				"rate": abs(flt(row.rate)),
				"amount": abs(flt(row.amount)),
			}
			for row in invoice.items
		],
		"subtotal": abs(flt(invoice.total)),
		"discounts": [
			{"label": row["label"], "amount": abs(row["amount"])} for row in get_order_discount_rows(invoice)
		],
		"charges": charges,
		"taxes": taxes,
		"total_taxes": total_taxes,
		"taxes_included": taxes_included,
		"taxable_value": taxes[0]["taxable_value"] if taxes else abs(flt(invoice.net_total)),
		"grand_total": abs(get_charge_amount(invoice)),
		"place_of_supply": invoice.get("place_of_supply"),
		"in_words": invoice.get("in_words"),
	}


def get_invoice_taxes(invoice) -> tuple[list[dict], list[dict]]:
	rule = get_shipping_rule_accounts(invoice.shipping_rule)
	taxable_values = get_taxable_values(invoice)
	taxes, charges = [], []
	for row in invoice.taxes:
		label = row.description or row.account_head
		amount = abs(flt(row.tax_amount_after_discount_amount))
		if get_charge_line_kind(row, rule) != "tax":
			charges.append({"label": label, "amount": amount})
			continue
		taxes.append(
			{
				"label": label,
				"rate": f"{flt(row.rate):g}%" if flt(row.rate) else None,
				"amount": amount,
				"taxable_value": abs(taxable_values.get(row.name, flt(invoice.net_total))),
				"included": bool(row.included_in_print_rate),
			}
		)
	if flt(invoice.rounding_adjustment) and not invoice.is_rounded_total_disabled():
		rounding = flt(invoice.rounding_adjustment)
		charges.append({"label": _("Rounding"), "amount": -rounding if invoice.is_return else rounding})
	return taxes, charges


def get_taxable_values(invoice) -> dict:
	taxable_values = {}
	for detail in invoice.get("item_wise_tax_details") or []:
		taxable_values[detail.tax_row] = taxable_values.get(detail.tax_row, 0) + flt(detail.taxable_amount)
	return taxable_values


def get_packing_slip_view(delivery_note) -> dict:
	sales_order = get_source_order(delivery_note, "against_sales_order")
	addresses = get_order_addresses(delivery_note)
	shipping = (
		addresses["shipping"] or addresses["billing"] or {"name": delivery_note.customer_name, "lines": []}
	)
	item_codes = [row.item_code for row in delivery_note.items]
	return {
		"doc": {
			"name": delivery_note.name,
			"packed_on": formatdate(delivery_note.posting_date),
			"order_name": sales_order.name if sales_order else delivery_note.name,
			"shipping": shipping,
			"contact_mobile": delivery_note.contact_mobile,
			"delivery_method": get_delivery_method(sales_order),
			"lines": [
				{**item, "item_code": item_code}
				for item, item_code in zip(get_order_items(delivery_note), item_codes, strict=True)
			],
			"total_qty": f"{flt(delivery_note.total_qty):g}",
		},
		"copy": {
			"closing": _("Something missing or wrong in this parcel? Write to us and quote the order number.")
		},
	}


def get_order_confirmation_view(sales_order) -> dict:
	items = get_order_items(sales_order)
	total = get_charge_amount(sales_order)
	return {
		"doc": {
			"name": sales_order.name,
			"transaction_date": formatdate(sales_order.transaction_date),
			"contact_email": sales_order.contact_email,
			"contact_mobile": sales_order.contact_mobile,
			"customer_tax_id": sales_order.tax_id,
			**get_order_addresses(sales_order),
			"facts": get_order_facts(sales_order, total),
			"lines": [
				{**item, **get_unit_prices(row)} for item, row in zip(items, sales_order.items, strict=True)
			],
			"totals": get_order_totals(sales_order, items, total),
		},
		"copy": {
			"heading": _("Thanks, {0}. Your order is in.").format(
				(sales_order.customer_name or "").split(" ")[0]
			),
			"intro": _("We've received your order and our team is getting it ready."),
			"closing": _("Need to change something? Write to us and quote the order number."),
		},
	}


def get_unit_prices(row) -> dict:
	rate = flt(row.rate) + flt(row.get("custom_code_discount"))
	was_rate = flt(row.price_list_rate)
	return {"item_code": row.item_code, "rate": rate, "was_rate": was_rate if was_rate > rate else None}


def get_source_order(doc, fieldname: str):
	order_name = next((row.get(fieldname) for row in doc.items if row.get(fieldname)), None)
	return frappe.get_doc("Sales Order", order_name) if order_name else None


def get_delivery_method(sales_order) -> str | None:
	if not sales_order:
		return None
	return (
		_("Store pickup")
		if sales_order.get("custom_is_store_pickup")
		else sales_order.get("custom_delivery_option")
	)
