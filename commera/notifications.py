import re

import frappe
from frappe import _, _lt
from frappe.contacts.doctype.address.address import get_company_address
from frappe.translate import print_language
from frappe.utils import flt, formatdate, get_url, strip_html

from commera.api.payments import COD_PAYMENT_MODE
from commera.api.shipping import get_charge_amount
from commera.branding import get_configured_brand_assets
from commera.discounts.allocations import get_price_discount_rows
from commera.localization.market_prices import MarketPrices
from commera.order_access import get_order_link, set_order_access_key
from commera.storefront_access import get_store_name
from commera.utils import get_item_images

EMAIL_SUBJECTS = {
	"order_confirmation": _lt("Order {order_number} confirmed"),
	"order_cancelled": _lt("Order {order_number} is cancelled"),
	"back_in_stock": _lt("{item_name} is back in stock"),
	"order_link": _lt("Your link to order {order_number}"),
	"sign_in_code": _lt("Your {store_name} sign-in code"),
}
CUSTOMER_EMAILS = tuple(EMAIL_SUBJECTS)
ALWAYS_ON_EMAILS = ("order_link", "sign_in_code")
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
):
	if not is_customer_email_enabled(email):
		return

	with print_language(language):
		args = {**args, "language": frappe.local.lang}
		content = get_email_content(email, get_customer_email_setting(email), args)
		frappe.sendmail(
			recipients=recipients,
			**content,
			wrapper=EMAIL_WRAPPER,
			add_css=False,
			add_unsubscribe_link=False,
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


def send_order_email(email: str, sales_order, recipients: list[str]):
	with print_language(sales_order.language):
		send_customer_email(
			email,
			recipients,
			get_order_context(sales_order),
			reference=sales_order,
			language=sales_order.language,
		)


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
