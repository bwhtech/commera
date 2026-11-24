import re

import frappe
from frappe import _, _lt
from frappe.contacts.doctype.address.address import get_company_address
from frappe.email.doctype.email_account.email_account import EmailAccount
from frappe.translate import print_language
from frappe.utils import cint, flt, formatdate, get_url, strip_html
from frappe.utils.jinja import get_email_from_template

from commera.api.payments import COD_PAYMENT_MODE
from commera.api.shipping import get_charge_amount
from commera.branding import get_configured_brand_assets
from commera.discounts.allocations import get_price_discount_rows
from commera.localization import StorefrontLanguages
from commera.localization.market_prices import MarketPrices
from commera.order_access import get_order_link, set_order_access_key
from commera.storefront_access import get_store_name
from commera.utils import get_item_images, get_return_deadline

EMAIL_SUBJECTS = {
	"order_confirmation": _lt("Order {order_number} confirmed"),
	"order_cancelled": _lt("Order {order_number} is cancelled"),
	"back_in_stock": _lt("{item_name} is back in stock"),
	"order_link": _lt("Your link to order {order_number}"),
	"sign_in_code": _lt("Your {store_name} sign-in code"),
	"order_shipped": _lt("Your order {order_number} has shipped"),
	"order_delivered": _lt("Your order {order_number} was delivered"),
	"order_refunded": _lt("Your refund for order {order_number} is on its way"),
	"order_returned": _lt("We received your return for order {order_number}"),
	"payment_failed": _lt("Your payment to {store_name} didn't go through"),
}
EMAIL_LABELS = {
	"order_confirmation": {
		"label": _lt("Order confirmation"),
		"description": _lt("Sent when a shopper places an order."),
	},
	"order_cancelled": {
		"label": _lt("Order cancelled"),
		"description": _lt("Sent when an order is cancelled."),
	},
	"back_in_stock": {
		"label": _lt("Back in stock"),
		"description": _lt("Sent to shoppers waiting on a product when it is restocked."),
	},
	"order_link": {
		"label": _lt("Order link"),
		"description": _lt("Sent when a guest asks for the link to their order."),
	},
	"sign_in_code": {
		"label": _lt("Sign-in code"),
		"description": _lt("Sent when a shopper signs in with their email address."),
	},
	"order_shipped": {
		"label": _lt("Order shipped"),
		"description": _lt("Sent when a parcel leaves your store, with its tracking."),
	},
	"order_delivered": {
		"label": _lt("Order delivered"),
		"description": _lt("Sent when the carrier confirms delivery."),
	},
	"order_refunded": {
		"label": _lt("Refund issued"),
		"description": _lt("Sent when you refund all or part of an order."),
	},
	"order_returned": {
		"label": _lt("Return received"),
		"description": _lt("Sent when returned items reach your store."),
	},
	"payment_failed": {
		"label": _lt("Payment failed"),
		"description": _lt("Sent when a shopper's card payment does not go through."),
	},
}
CUSTOMER_EMAILS = tuple(EMAIL_SUBJECTS)
ALWAYS_ON_EMAILS = ("order_link", "sign_in_code")
EVENT_EMAILS = {
	"order_placed": "order_confirmation",
	"order_cancelled": "order_cancelled",
	"order_shipment_dispatched": "order_shipped",
	"order_delivered": "order_delivered",
	"order_refunded": "order_refunded",
	"order_returned": "order_returned",
}
PAYMENT_FAILED_STATUSES = ("Not Paid",)
INVOICE_PRINT_FORMAT = "Commera Invoice"
ATTACHED_INVOICES = {"order_confirmation": False, "order_refunded": True}
EMAIL_WRAPPER = "templates/emails/commera_document.html"


def get_template_name(email: str) -> str:
	return f"commera_{email}"


def seed_customer_emails():
	settings = frappe.get_single("Commera Settings")
	existing = {row.email for row in settings.customer_emails}
	for email in CUSTOMER_EMAILS:
		if email not in existing:
			settings.append(
				"customer_emails", {"email": email, "enabled": 1, "template": get_template_name(email)}
			).db_insert()


def validate_customer_emails(settings):
	seen = set()
	for row in settings.customer_emails:
		if row.email in seen:
			frappe.throw(_("The {0} email is listed twice.").format(row.email))
		seen.add(row.email)
		row.template = get_template_name(row.email)
		if row.email in ALWAYS_ON_EMAILS and not row.enabled:
			frappe.throw(
				_(
					"The {0} email cannot be turned off: shoppers need it to sign in or open their order."
				).format(row.email)
			)


def get_customer_email_setting(email: str):
	settings = frappe.get_cached_doc("Commera Settings")
	return next((row for row in settings.customer_emails if row.email == email), None)


def is_customer_email_enabled(email: str) -> bool:
	setting = get_customer_email_setting(email)
	return not setting or bool(setting.enabled)


def send_customer_email(
	email: str,
	recipients: list[str],
	args: dict,
	reference=None,
	language: str | None = None,
	now: bool = False,
	attachments: list[dict] | None = None,
):
	if not is_customer_email_enabled(email):
		return
	deliver_customer_email(email, recipients, args, reference, language, now, attachments)


def deliver_customer_email(
	email: str,
	recipients: list[str],
	args: dict,
	reference=None,
	language: str | None = None,
	now: bool = False,
	attachments: list[dict] | None = None,
):
	with print_language(language):
		args = {**args, "language": frappe.local.lang}
		content = get_email_content(email, get_customer_email_setting(email), args)
		frappe.sendmail(
			recipients=recipients,
			**content,
			wrapper=EMAIL_WRAPPER,
			add_css=False,
			add_unsubscribe_link=False,
			attachments=attachments,
			reference_doctype=reference.doctype if reference else None,
			reference_name=reference.name if reference else None,
			now=now,
		)


def get_email_content(email: str, setting, args: dict) -> dict:
	if setting and setting.email_template:
		try:
			return frappe.get_doc("Email Template", setting.email_template).get_formatted_email(dict(args))
		except Exception:
			if email not in ALWAYS_ON_EMAILS:
				raise
			frappe.log_error(title=_("Custom {0} email failed, sent the built-in one").format(email))
	return {
		"subject": str(EMAIL_SUBJECTS[email]).format(**args),
		"template": get_template_name(email),
		"args": args,
	}


def render_customer_email(email: str, args: dict) -> dict:
	content = get_email_content(email, get_customer_email_setting(email), args)
	if "message" in content:
		return {"subject": content["subject"], "html": content["message"]}
	html = get_email_from_template(content["template"], content["args"])[0]
	return {"subject": content["subject"], "html": html}


def send(event):
	if not frappe.flags.mute_emails and not EmailAccount.find_outgoing():
		return
	email = EVENT_EMAILS[event.name]
	sales_order = frappe.get_doc("Sales Order", event.reference_name)
	recipient = get_order_recipient(sales_order)
	if recipient:
		send_order_email(email, sales_order, [recipient], event.data)


def get_order_recipient(sales_order) -> str | None:
	return sales_order.contact_email or get_portal_user_email(sales_order.customer)


def get_portal_user_email(customer: str) -> str | None:
	portal_users = frappe.get_all("Portal User", {"parent": customer}, pluck="user", limit=1)
	return portal_users[0] if portal_users else None


def send_order_email(email: str, sales_order, recipients: list[str], event_data: dict | None = None):
	if not is_customer_email_enabled(email):
		return
	with print_language(sales_order.language):
		context = get_order_context(sales_order)
		if add_context := EMAIL_CONTEXT.get(email):
			add_context(context, sales_order, event_data or {})
		send_customer_email(
			email,
			recipients,
			context,
			reference=sales_order,
			language=sales_order.language,
			attachments=get_order_attachments(email, sales_order),
		)


def add_shipped_context(context: dict, sales_order, event_data: dict):
	shipped_lines = event_data.get("line_items")
	order = context["order"]
	if shipped_lines:
		order["parcel_items"] = get_parcel_items(sales_order, order["line_items"], shipped_lines)
		shipped_qty = sum(flt(line.get("qty")) for line in shipped_lines)
		order["partial"] = shipped_qty < sum(flt(row.qty) for row in sales_order.items)
	else:
		order["parcel_items"] = []
		order["partial"] = sales_order.get("custom_ecommerce_status") == "Partially Shipped"
	context["shipment"] = {
		"carrier": event_data.get("carrier"),
		"awb": event_data.get("awb"),
		"tracking_url": event_data.get("tracking_url"),
	}


def get_parcel_items(sales_order, order_items: list[dict], shipped_lines: list[dict]) -> list[dict]:
	ordered_qty = {}
	for row in sales_order.items:
		ordered_qty[row.item_code] = ordered_qty.get(row.item_code, 0) + flt(row.qty)
	items_by_code = {item["item_code"]: item for item in order_items}
	parcel_items = []
	for line in shipped_lines:
		item = items_by_code.get(line.get("item_code"))
		if not item or not ordered_qty.get(item["item_code"]):
			continue
		share = flt(line.get("qty")) / ordered_qty[item["item_code"]]
		parcel_items.append(
			{
				**item,
				"qty": f"{flt(line.get('qty')):g}",
				"amount": item["amount"] * share,
				"was_amount": item["was_amount"] * share if item["was_amount"] else None,
			}
		)
	return parcel_items


def add_delivered_context(context: dict, sales_order, event_data: dict):
	return_period = cint(frappe.get_cached_doc("Commera Settings").return_period)
	return_deadline = get_return_deadline(sales_order.name, return_period) if return_period else None
	context["order"]["return_by"] = formatdate(return_deadline) if return_deadline else None


def add_refunded_context(context: dict, sales_order, event_data: dict):
	payment_entry = frappe.db.get_value(
		"Payment Entry", event_data.get("payment_entry"), ["posting_date", "mode_of_payment"], as_dict=True
	)
	context["refund"] = {
		"amount": flt(event_data.get("amount")),
		"refunded_on": formatdate(payment_entry.posting_date) if payment_entry else None,
		"method": payment_entry.mode_of_payment if payment_entry else None,
	}


def add_returned_context(context: dict, sales_order, event_data: dict):
	return_lines = frappe.get_all(
		"Delivery Note Item",
		filters={
			"against_sales_order": sales_order.name,
			"parenttype": "Delivery Note",
			"docstatus": 1,
			"qty": ("<", 0),
		},
		fields=["parent", "item_code", "item_name", "qty", "creation"],
		order_by="creation desc",
	)
	latest_return = return_lines[0].parent if return_lines else None
	received_on = return_lines[0].creation if return_lines else None
	context["returned"] = {
		"name": latest_return,
		"received_on": formatdate(received_on) if received_on else None,
		"items": get_parcel_items(
			sales_order,
			context["order"]["line_items"],
			[{"item_code": line.item_code, "qty": abs(flt(line.qty))} for line in return_lines],
		),
	}


EMAIL_CONTEXT = {
	"order_shipped": add_shipped_context,
	"order_delivered": add_delivered_context,
	"order_refunded": add_refunded_context,
	"order_returned": add_returned_context,
}


def send_payment_failed_email(payment_request):
	if payment_request.status not in PAYMENT_FAILED_STATUSES or payment_request.ref_doctype != "Quotation":
		return
	before_save = payment_request.get_doc_before_save()
	if before_save and before_save.status in PAYMENT_FAILED_STATUSES:
		return
	quotation = frappe.get_doc("Quotation", payment_request.ref_docname)
	recipient = quotation.contact_email or payment_request.customer_email
	if not recipient or not is_customer_email_enabled("payment_failed"):
		return
	with print_language(quotation.language):
		send_customer_email(
			"payment_failed",
			[recipient],
			get_payment_failed_context(quotation, payment_request),
			reference=quotation,
			language=quotation.language,
		)


def get_payment_failed_context(quotation, payment_request) -> dict:
	items = get_order_items(quotation)
	total = get_charge_amount(quotation)
	languages = StorefrontLanguages.load()
	language = languages.find(quotation.language) or languages.default
	return {
		"brand": get_brand_context(quotation.company),
		"store_name": get_store_name(),
		"first_name": (quotation.customer_name or "").split(" ")[0],
		"cart_url": get_url(f"/{language.code.lower()}/cart"),
		"payment": {"amount": flt(payment_request.amount), "method": payment_request.gateway},
		"order": {
			"name": quotation.name,
			"currency": quotation.currency,
			"line_items": items,
			"totals": get_order_totals(quotation, items, total),
		},
	}


def get_invoice_print_format() -> str:
	return (
		frappe.get_cached_value("Commera Settings", "Commera Settings", "print_format")
		or INVOICE_PRINT_FORMAT
	)


def get_order_attachments(email: str, sales_order) -> list[dict]:
	is_return = ATTACHED_INVOICES.get(email)
	if is_return is None or (not is_return and sales_order.custom_ecommerce_payment_mode == COD_PAYMENT_MODE):
		return []
	invoices = frappe.get_all(
		"Sales Invoice",
		filters=[
			["Sales Invoice Item", "sales_order", "=", sales_order.name],
			["docstatus", "=", 1],
			["is_return", "=", int(is_return)],
		],
		pluck="name",
		order_by="creation desc",
		limit=1,
	)
	return [
		{
			"print_format_attachment": 1,
			"doctype": "Sales Invoice",
			"name": invoice,
			"print_format": get_invoice_print_format(),
			"lang": frappe.local.lang,
		}
		for invoice in invoices
	]


def get_brand_context(company: str | None = None) -> dict:
	company = company or frappe.get_cached_doc("Commera Settings").company
	name = get_store_name() or company or ""
	logo = get_configured_brand_assets()["logo"]
	company_address = get_company_address(company).get("company_address_display") if company else None
	return {
		"name": name,
		"initial": name[:1].upper(),
		"logo": get_url(logo) if logo else None,
		"url": get_url(),
		"legal_name": company,
		"address": ", ".join(get_address_lines(company_address)),
		"tax_id": frappe.get_cached_value("Company", company, "tax_id") if company else None,
	}


def get_order_context(sales_order) -> dict:
	set_order_access_key(sales_order)
	order_link = get_order_link(sales_order)
	total = get_charge_amount(sales_order)
	items = get_order_items(sales_order)
	return {
		"brand": get_brand_context(sales_order.company),
		"order_number": sales_order.name,
		"store_name": get_store_name(),
		"first_name": (sales_order.customer_name or "").split(" ")[0],
		"order": {
			"name": sales_order.name,
			"transaction_date": formatdate(sales_order.transaction_date),
			"currency": sales_order.currency,
			"line_items": items,
			"totals": get_order_totals(sales_order, items, total),
			"paid_amount": flt(sales_order.advance_paid),
			"payment_mode": sales_order.custom_ecommerce_payment_mode,
			"contact_mobile": sales_order.contact_mobile,
			"tax_id": sales_order.tax_id,
			**get_order_addresses(sales_order),
			"facts": get_order_facts(sales_order, total),
			"link": order_link,
			"links": [{"label": _("Track order"), "url": order_link}] if order_link else [],
		},
	}


def get_order_items(sales_order) -> list[dict]:
	item_codes = [row.item_code for row in sales_order.items]
	images = get_item_images(item_codes)
	variants = get_variant_labels(item_codes)
	items = []
	for row in sales_order.items:
		amount = flt(row.amount) + flt(row.get("custom_code_discount")) * flt(row.qty)
		was_amount = flt(row.price_list_rate) * flt(row.qty)
		image = images.get(row.item_code) or row.image
		items.append(
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"variant": variants.get(row.item_code),
				"qty": f"{flt(row.qty):g}",
				"amount": amount,
				"was_amount": was_amount if was_amount > amount else None,
				"image": get_url(image) if image else None,
			}
		)
	return items


def get_variant_labels(item_codes: list[str]) -> dict:
	if not item_codes:
		return {}
	attribute = frappe.qb.DocType("Item Variant Attribute")
	rows = (
		frappe.qb.from_(attribute)
		.select(attribute.parent, attribute.attribute_value)
		.where(
			(attribute.parenttype == "Item")
			& attribute.parent.isin(item_codes)
			& (attribute.attribute_value.notnull())
			& (attribute.attribute_value != "")
		)
		.orderby(attribute.idx)
	).run(as_dict=True)
	values_by_item = {}
	for row in rows:
		values_by_item.setdefault(row.parent, []).append(row.attribute_value)
	return {item_code: ", ".join(values) for item_code, values in values_by_item.items()}


def get_order_totals(sales_order, items: list[dict], total: float) -> dict:
	charges = [tax for tax in sales_order.taxes if not tax.included_in_print_rate]
	included = [tax for tax in sales_order.taxes if tax.included_in_print_rate]
	return {
		"subtotal": sum(item["amount"] for item in items),
		"discounts": get_price_discount_rows(sales_order),
		"charges": [
			{"label": tax.description or tax.account_head, "amount": flt(tax.tax_amount)} for tax in charges
		],
		"included_taxes": [
			{"label": tax.description or tax.account_head, "amount": flt(tax.tax_amount)} for tax in included
		],
		"total": total,
	}


def get_order_addresses(sales_order) -> dict:
	address_names = {sales_order.shipping_address_name, sales_order.customer_address} - {None, ""}
	titles = dict(
		frappe.get_all(
			"Address",
			filters={"name": ("in", list(address_names))},
			fields=["name", "address_title"],
			as_list=True,
		)
		if address_names
		else ()
	)
	shipping_lines = get_address_lines(sales_order.shipping_address)
	shipping = (
		{
			"name": titles.get(sales_order.shipping_address_name) or sales_order.customer_name,
			"lines": shipping_lines,
		}
		if shipping_lines
		else None
	)
	billing = None
	if sales_order.customer_address and sales_order.customer_address != sales_order.shipping_address_name:
		billing = {
			"name": titles.get(sales_order.customer_address) or sales_order.customer_name,
			"lines": get_address_lines(sales_order.address_display),
		}
	return {"shipping": shipping, "billing": billing}


def get_address_lines(address_display: str | None) -> list[str]:
	lines = re.split(r"<br\s*/?>|\n", address_display or "")
	cleaned_lines = (strip_html(line).strip().strip(",") for line in lines)
	return [line for line in cleaned_lines if line]


def get_order_facts(sales_order, total: float) -> list[dict]:
	payment_mode = sales_order.custom_ecommerce_payment_mode
	if payment_mode == COD_PAYMENT_MODE:
		payment_detail = _("Pay on delivery")
	elif flt(sales_order.advance_paid) and flt(sales_order.advance_paid) >= flt(total):
		payment_detail = _("Paid")
	else:
		payment_detail = None
	delivery = (
		_("Store pickup")
		if sales_order.get("custom_is_store_pickup")
		else sales_order.get("custom_delivery_option")
	)
	facts = []
	if payment_mode:
		facts.append({"label": _("Payment"), "title": _(payment_mode), "detail": payment_detail})
	if delivery:
		facts.append({"label": _("Delivery"), "title": delivery, "detail": None})
	return facts


def get_back_in_stock_context(item_code: str, style_attribute_variant) -> dict:
	prices = MarketPrices.of(None)
	sale, compare_at = prices.get_base_rates([item_code])
	price = prices.price(sale.get(item_code), compare_at.get(item_code))
	image = get_item_images([item_code]).get(item_code)
	return {
		"brand": get_brand_context(),
		"store_name": get_store_name(),
		"item_name": style_attribute_variant.display_name,
		"currency": prices.currency,
		"product": {
			"item_name": style_attribute_variant.display_name,
			"variant": get_variant_labels([item_code]).get(item_code),
			"price": price,
			"was_price": prices.compare_at(price, compare_at.get(item_code)),
			"image": get_url(image) if image else None,
		},
	}
