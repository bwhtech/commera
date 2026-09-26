from contextlib import contextmanager

import frappe
from bwh_payments.bwh_payments.utils import get_available_payment_modes, resolve_payment_mode
from erpnext.accounts.doctype.journal_entry.journal_entry import get_default_bank_cash_account
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.doctype.pricing_rule.utils import validate_coupon_code
from frappe import _
from frappe.utils import getdate, validate_email_address
from frappe.utils.data import cstr, flt, fmt_money

from commera.analytics.events import log_purchase, set_attribution_fields
from commera.api.cart import validate_stock_available
from commera.api.shipping import (
	add_cod_charge,
	clear_delivery_option,
	clear_pickup_charges,
	copy_delivery_option_to_order,
	get_charge_amount,
	get_checkout_summary,
	get_cod_charge,
	reprice_selected_option,
)
from commera.core import _get_cart_quotation
from commera.utils import get_pickup_addresses, get_pickup_warehouses


class CheckoutPriceChangedError(frappe.ValidationError):
	pass


# ERPNext moved its transaction mappers to a sibling `mapper` module; both layouts are in the wild.
try:
	from erpnext.selling.doctype.quotation.mapper import _make_sales_order
except ImportError:
	from erpnext.selling.doctype.quotation.quotation import _make_sales_order

try:
	from erpnext.selling.doctype.sales_order.mapper import make_sales_invoice
except ImportError:
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

COD_PAYMENT_MODE = "COD"


def is_cod(payment_mode: str | None) -> bool:
	return (payment_mode or "").strip().casefold() == COD_PAYMENT_MODE.casefold()


def get_open_gateway_payment_request(quotation_name: str) -> str | None:
	for status in ("Paid", "Pending"):
		open_request = frappe.db.get_value(
			"Gateway Payment Request",
			{"ref_doctype": "Quotation", "ref_docname": quotation_name, "status": status},
			"name",
		)
		if open_request:
			return open_request

	return None


def validate_cart_is_not_in_checkout(quotation_name: str):
	if not quotation_name:
		return

	if frappe.db.exists(
		"Gateway Payment Request",
		{"ref_doctype": "Quotation", "ref_docname": quotation_name, "status": "Paid"},
	):
		refuse_paid_cart()

	# A double-clicked Place Order leaves two open sessions, and each one still bills the old cart.
	pending_requests = frappe.get_all(
		"Gateway Payment Request",
		filters={"ref_doctype": "Quotation", "ref_docname": quotation_name, "status": "Pending"},
		pluck="name",
	)
	for pending_request in pending_requests:
		payment_request = frappe.get_doc("Gateway Payment Request", pending_request)
		if payment_request.release_if_unpaid():
			continue
		if payment_request.status == "Paid":
			refuse_paid_cart()
		frappe.throw(
			_(
				"A payment is already in progress for this order. Finish or cancel it before changing your cart."
			),
			title=_("Checkout In Progress"),
		)


def refuse_paid_cart():
	frappe.throw(
		_("This order has already been paid. Open it from your account rather than changing the cart."),
		title=_("Already Paid"),
	)


def get_confirmation_url(reference_id: str, payment_mode: str | None = None) -> str:
	url = f"/{frappe.local.lang}/account/orders/confirmation?reference_id={reference_id}"
	if payment_mode:
		url = f"{url}&payment_mode={payment_mode}"
	return url


def refuse_payment(message: str, quotation: str | None = None, **context):
	details = {"quotation": quotation, "user": frappe.session.user, **context}
	frappe.log_error(
		title=f"Checkout refused: {message}"[:140],
		message="\n".join(f"{key}: {value}" for key, value in details.items()),
		reference_doctype="Quotation" if quotation else None,
		reference_name=quotation,
		defer_insert=True,
	)
	frappe.throw(message)


@frappe.whitelist(methods=["POST"])
def initiate_checkout_with_mode(
	payment_mode: str, delivery_option: str | None = None, expected_total: float | None = None
):
	quotation = _get_cart_quotation()
	with cart_write_lock(quotation):
		return open_checkout(quotation, payment_mode, delivery_option, expected_total)


def open_checkout(
	quotation, payment_mode: str, delivery_option: str | None = None, expected_total: float | None = None
):
	validate_delivery_option(quotation, delivery_option)
	validate_cart_is_not_in_checkout(quotation.name)
	update_delivery_charges(quotation)
	validate_expected_total(quotation, payment_mode, expected_total)

	if is_cod(payment_mode):
		if not frappe.db.get_single_value("Commera Settings", "cod_enabled"):
			refuse_payment(_("Cash on delivery is not available."), quotation.name)
		return {"order_url": get_confirmation_url(quotation.name, payment_mode=COD_PAYMENT_MODE)}

	gateway = resolve_payment_mode(payment_mode)
	if not gateway:
		refuse_payment(
			_("Please select a valid payment mode."),
			quotation.name,
			requested=payment_mode,
			available=get_available_payment_modes(),
		)

	customer_contact = (
		frappe.db.get_value(
			"Contact",
			quotation.contact_person,
			["email_id", "first_name", "last_name"],
			as_dict=True,
		)
		or frappe._dict()
	)
	customer_phone = frappe.db.get_value(
		"Contact Phone",
		{"parent": quotation.contact_person, "parenttype": "Contact", "idx": 1},
		"phone",
	)

	payment_request = frappe.get_doc(
		{
			"doctype": "Gateway Payment Request",
			"gateway": gateway,
			"amount": get_charge_amount(quotation),
			"currency_code": quotation.currency,
			"company": quotation.company,
			"ref_doctype": quotation.doctype,
			"ref_docname": quotation.name,
			"customer_ref": quotation.party_name,
			"customer_phone": customer_phone,
			"customer_forenames": customer_contact.first_name,
			"customer_surname": customer_contact.last_name,
			"customer_email": get_gateway_email(customer_contact.email_id),
			"customer_address": quotation.customer_address,
		}
	).insert(ignore_permissions=True)

	return {"order_url": payment_request.order_url}


def validate_delivery_option(quotation, delivery_option: str | None):
	# Payment reprices the stored option, so it must be the one the shopper is looking at.
	if cstr(quotation.custom_delivery_option) == cstr(delivery_option):
		return

	frappe.throw(
		_("Your delivery option has changed. Please choose it again before placing your order."),
		title=_("Delivery Option Changed"),
		exc=CheckoutPriceChangedError,
	)


def validate_expected_total(quotation, payment_mode: str, expected_total: float | None):
	# A re-quote past the rates cache, or a flat rule edited meanwhile, must not bill a figure never shown.
	if expected_total is None:
		return

	payable_total = get_payable_total(quotation, payment_mode)
	precision = quotation.precision("grand_total")
	if flt(expected_total, precision) == flt(payable_total, precision):
		return

	frappe.throw(
		_("Your order total has changed to {0}. Please review it before placing your order.").format(
			fmt_money(payable_total, currency=quotation.currency)
		),
		title=_("Order Total Changed"),
		exc=CheckoutPriceChangedError,
	)


def get_payable_total(quotation, payment_mode: str) -> float:
	if is_cod(payment_mode):
		return get_checkout_summary(quotation)["cash_on_delivery"]["total"]
	return get_charge_amount(quotation)


def get_gateway_email(contact_email: str | None) -> str | None:
	if valid_email := validate_email_address(contact_email or "", throw=False):
		return valid_email

	if frappe.session.user == "Guest":
		return None

	user_email = frappe.db.get_value("User", frappe.session.user, "email")
	return validate_email_address(user_email or "", throw=False) or None


def gateway_mode_of_payment(gateway: str) -> str:
	mode_of_payment = frappe.db.get_value("Mode of Payment", (gateway or "").strip(), "name")
	if not mode_of_payment:
		frappe.throw(_("No Mode of Payment found matching gateway {0}").format(frappe.bold(gateway)))
	return mode_of_payment


@contextmanager
def system_user_session():
	"""Place the accounting documents as Administrator, then hand the session back.

	ERPNext's get_party_account checks frappe.has_permission directly, so no ignore_permissions reaches it.
	"""
	# frappe.set_user() mutates frappe.local.session in place, stamping "sid" with the username and wiping
	# local.session.data, so restore the snapshot verbatim rather than calling it again for the shopper.
	live_session_snapshot = frappe.local.session.copy()
	try:
		# Audited: the docstring above and the snapshot restore below are why this is safe.
		frappe.set_user("Administrator")  # nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
		yield
	finally:
		frappe.local.session.update(live_session_snapshot)
		frappe.local.cache = {}
		frappe.local.role_permissions = {}
		frappe.local.user_perms = None


@contextmanager
def cart_write_lock(quotation):
	if quotation.is_new():
		yield quotation
		return

	quotation.flags.for_update = True
	quotation.reload()
	yield quotation


def save_cart_quotation(quotation):
	"""Persist the shopper's own cart, elevated. Saving resolves the receivable account, and ERPNext's
	account_perm_check calls frappe.has_permission("Account") directly - no ignore_permissions reaches it."""
	with system_user_session():
		quotation.flags.ignore_permissions = True
		return quotation.save()


def stamp_order_owner(sales_order, shopper: str) -> None:
	"""Hand the order back to the shopper who bought it: insert() runs as Administrator (see
	system_user_session), and every post-purchase screen gates on owner == frappe.session.user."""
	if not shopper or shopper == sales_order.owner:
		return
	sales_order.db_set("owner", shopper, update_modified=False)


def place_order(quotation, payment_mode: str, gateway_amount=None, gateway_reference=None):
	"""Submit the cart and bill it. Called once per payment; the Quotation docstatus enforces that."""
	shopper = frappe.session.user
	with system_user_session():
		fix_payment_schedule_dates(quotation)
		quotation.flags.ignore_permissions = True
		quotation.submit()

		sales_order = _make_sales_order(quotation.name, ignore_permissions=True)
		sales_order.custom_ecommerce_payment_mode = payment_mode
		copy_delivery_option_to_order(quotation.name, sales_order)
		fix_payment_schedule_dates(sales_order)
		set_attribution_fields(sales_order)
		sales_order.flags.ignore_permissions = True
		sales_order.insert()
		sales_order.submit()

		if flt(gateway_amount) > 0:
			create_sales_invoice(sales_order, payment_mode, flt(gateway_amount), gateway_reference)

	# Outside the switch: log_purchase stamps frappe.session.user, so Administrator would own every purchase.
	stamp_order_owner(sales_order, shopper)
	log_purchase(sales_order)
	return sales_order


def create_sales_invoice(sales_order, payment_mode: str, paid_amount: float, reference_no: str | None):
	sales_invoice = make_sales_invoice(sales_order.name, ignore_permissions=True)
	sales_invoice.flags.ignore_permissions = True
	sales_invoice.insert()
	sales_invoice.submit()
	create_payment_entry(sales_invoice, payment_mode, paid_amount, reference_no)
	return sales_invoice


def create_payment_entry(sales_invoice, payment_mode: str, paid_amount: float, reference_no: str | None):
	# Never allocate more than the invoice owes, whatever the gateway reported.
	allocated = min(flt(paid_amount), flt(sales_invoice.outstanding_amount))
	if allocated <= 0:
		return None

	payment_entry = get_payment_entry("Sales Invoice", sales_invoice.name, party_amount=allocated)
	payment_entry.mode_of_payment = gateway_mode_of_payment(payment_mode)
	if reference_no:
		# Load-bearing: bwh_payments matches a refund Payment Entry back to its gateway session on this.
		payment_entry.reference_no = reference_no
		payment_entry.reference_date = getdate()

	bank = get_default_bank_cash_account(
		sales_invoice.company, "Cash", mode_of_payment=payment_entry.mode_of_payment
	)
	if bank:
		payment_entry.paid_to = bank.account
		payment_entry.paid_to_account_currency = bank.account_currency

	payment_entry.flags.ignore_permissions = True
	payment_entry.insert()
	payment_entry.submit()
	return payment_entry


def fix_payment_schedule_dates(doc):
	today = getdate()
	for term in doc.get("payment_schedule", []):
		if term.due_date and term.due_date < today:
			term.due_date = today


@frappe.whitelist(methods=["POST"])
def generate_quotation_for_cart(cart: dict):
	cart = frappe.parse_json(cart)
	if len(cart.get("items", [])) < 1:
		frappe.throw(_("Can't checkout with empty cart"))
	validate_stock_available(cart["items"])
	quotation = _get_cart_quotation()
	validate_cart_is_not_in_checkout(quotation.name)
	cart_quotation = get_quotation_for_cart(cart, quotation)
	remove_coupon_code()
	return cart_quotation


def get_quotation_for_cart(cart: dict, unsaved_quotation_doc):
	sale_price_list = frappe.get_cached_value("Commera Settings", "Commera Settings", "sale_price_list")
	ecommerce_warehouse = frappe.get_cached_value(
		"Commera Settings", "Commera Settings", "ecommerce_warehouse"
	)
	unsaved_quotation_doc.selling_price_list = sale_price_list
	set_attribution_fields(unsaved_quotation_doc)
	unsaved_quotation_doc.items = []
	for item in cart["items"]:
		unsaved_quotation_doc.append(
			"items",
			{
				"item_code": item["variant"]["item_code"],
				"qty": item["qty"],
				"warehouse": ecommerce_warehouse,
			},
		)
	save_cart_quotation(unsaved_quotation_doc)
	# The stored option was priced for the old cart, and payment would re-quote it for the new one.
	clear_delivery_option(unsaved_quotation_doc)
	_remove_coupon_code(unsaved_quotation_doc)
	set_charges(unsaved_quotation_doc)
	return save_cart_quotation(unsaved_quotation_doc)


def set_charges(quotation):
	shipping_rule = frappe.get_cached_value("Commera Settings", "Commera Settings", "shipping_rule")
	if shipping_rule:
		quotation.shipping_rule = shipping_rule
		quotation.run_method("apply_shipping_rule")
		quotation.run_method("calculate_taxes_and_totals")


def set_cod_charges(quotation):
	cod_charge = get_cod_charge(quotation)
	if not cod_charge:
		return
	account_head = frappe.get_cached_value("Commera Settings", "Commera Settings", "charge_account_head")
	if not account_head:
		frappe.throw(_("Please select a valid account for cod charges."))

	add_cod_charge(quotation, cod_charge, account_head)
	quotation.flags.ignore_permissions = True
	quotation.save()


@frappe.whitelist(methods=["POST"])
def update_quotation_address(address: dict):
	quotation = _get_cart_quotation()
	with cart_write_lock(quotation):
		return save_quotation_address(quotation, address)


def save_quotation_address(quotation, address: dict):
	validate_cart_is_not_in_checkout(quotation.name)
	update_quotation_payment_terms_due_date(quotation)
	if address.get("is_store_pickup", False):
		validate_store_pickup(address.get("store_pickup_warehouse"))
		quotation.custom_store = address.get("store_pickup_warehouse")
		quotation.custom_is_store_pickup = True
		# A delivery option picked before store pickup would otherwise still be charged at payment time.
		clear_delivery_option(quotation)
		save_cart_quotation(quotation)

		return get_address_saved_response(quotation)
	quotation.custom_is_store_pickup = False
	quotation.custom_store = ""

	if address.get("billing_address", {}).get("is_saved"):
		billing_address_name = address.get("billing_address", {}).get("address_id")
	else:
		billing_address_doc = add_billing_address(quotation.party_name, address)
		billing_address_name = billing_address_doc.name

	quotation.customer_address = billing_address_name

	if address.get("shipping_same_as_billing"):
		shipping_address_name = billing_address_name
	elif address.get("shipping_address", {}).get("is_saved"):
		shipping_address_name = address.get("shipping_address", {}).get("address_id")
	else:
		shipping_address_doc = add_shipping_address(quotation.party_name, address)
		shipping_address_name = shipping_address_doc.name

	quotation.shipping_address_name = shipping_address_name
	clear_delivery_option(quotation)
	set_gst_details(quotation)

	contact = frappe.get_doc("Contact", quotation.contact_person)
	existing_phones = {entry.phone for entry in contact.phone_nos}

	billing_phone = address.get("billing_address", {}).get("phone_number")
	if billing_phone and billing_phone not in existing_phones:
		contact.append("phone_nos", {"phone": billing_phone})

	shipping_phone = address.get("shipping_address", {}).get("phone_number")
	if shipping_phone and shipping_phone not in existing_phones:
		contact.append("phone_nos", {"phone": shipping_phone})

	contact.save(ignore_permissions=True)
	save_cart_quotation(quotation)

	return get_address_saved_response(quotation)


def get_address_saved_response(quotation) -> dict:
	return {
		"message": _("Addresses updated successfully"),
		"checkout_summary": get_checkout_summary(quotation),
	}


def set_gst_details(quotation):
	if "india_compliance" not in frappe.get_installed_apps():
		return

	from india_compliance.gst_india.overrides.transaction import get_gst_details

	party_details = quotation.as_dict()
	party_details.gst_category = frappe.db.get_value("Address", quotation.customer_address, "gst_category")
	gst_details = get_gst_details(
		party_details, quotation.doctype, quotation.company, update_place_of_supply=True
	)
	quotation.update(gst_details)
	if party_details.gst_category:
		quotation.gst_category = party_details.gst_category
	set_charges(quotation)


@frappe.whitelist()
def confirm_payment(reference_id: str, payment_mode: str | None = None):
	"""Resolve the outcome of a checkout the shopper has just come back from.

	`reference_id` is a Gateway Payment Request (name or gateway session id), or the Quotation for COD.
	"""
	payment_request = get_gateway_payment_request(reference_id)
	if payment_request:
		validate_reference_owner(payment_request.ref_doctype, payment_request.ref_docname)
		if is_cod(payment_mode):
			# payment_mode is attacker-controlled: without this, &payment_mode=COD double-books a paid cart.
			refuse_payment(
				_("A card payment is already in progress for this order."),
				payment_request.ref_docname,
				payment_request=payment_request.name,
			)
		if payment_request.status == "Pending":
			payment_request.sync_status()
		return {"status": payment_request.status, **purchase_summary(payment_request)}

	validate_reference_owner("Quotation", reference_id)
	if frappe.db.get_value("Quotation", reference_id, "docstatus") == 1:
		return {"status": "Paid", **quotation_purchase_summary(reference_id)}

	if not is_cod(payment_mode):
		refuse_payment(_("No payment record found for this order."), reference_id)
	if not frappe.db.get_single_value("Commera Settings", "cod_enabled"):
		refuse_payment(_("Cash on delivery is not available."), reference_id)

	sales_order = place_cod_order(reference_id)
	return {"status": "Paid", **sales_order_purchase_summary(sales_order)}


def get_gateway_payment_request(reference_id: str):
	"""Look a request up by gateway session id, then by our own name, then by the Quotation it opened against.

	The Quotation fallback is what stops the COD branch running on a cart with a live gateway session.
	"""
	name = frappe.db.get_value("Gateway Payment Request", {"order_ref": reference_id}, "name")
	name = name or frappe.db.get_value("Gateway Payment Request", reference_id, "name")
	name = name or get_open_gateway_payment_request(reference_id)
	return frappe.get_doc("Gateway Payment Request", name) if name else None


def validate_reference_owner(doctype: str, docname: str):
	# Scoped to the cart's own contact, so a forged reference simply finds nothing.
	if not frappe.db.exists(doctype, {"name": docname, "contact_email": frappe.session.user}):
		raise frappe.PermissionError


def purchase_summary(payment_request):
	if payment_request.ref_doctype == "Sales Order":
		return sales_order_purchase_summary(frappe.get_doc("Sales Order", payment_request.ref_docname))
	return quotation_purchase_summary(payment_request.ref_docname)


def sales_order_purchase_summary(sales_order):
	# order_name must match events.log_purchase's order_id, or Meta will not dedupe the two Purchase hits.
	if not sales_order:
		return {}
	return {
		"order_name": sales_order.name,
		"grand_total": sales_order.grand_total,
		"currency": sales_order.currency,
	}


def quotation_purchase_summary(quotation_name: str):
	sales_order = frappe.db.get_value(
		"Sales Order Item", {"prevdoc_docname": quotation_name, "docstatus": 1}, "parent"
	)
	if sales_order:
		return sales_order_purchase_summary(frappe.get_doc("Sales Order", sales_order))

	quotation = frappe.db.get_value("Quotation", quotation_name, ["grand_total", "currency"], as_dict=True)
	return {
		"order_name": quotation_name,
		"grand_total": quotation.grand_total if quotation else 0,
		"currency": quotation.currency if quotation else None,
	}


def place_cod_order(quotation_name: str):
	shopper = frappe.session.user
	with system_user_session():
		quotation = frappe.get_doc("Quotation", quotation_name)
		set_cod_charges(quotation)
		quotation.flags.ignore_permissions = True
		quotation.submit()

		sales_order = _make_sales_order(quotation_name, ignore_permissions=True)
		sales_order.custom_ecommerce_payment_mode = COD_PAYMENT_MODE
		set_attribution_fields(sales_order)
		sales_order.flags.ignore_permissions = True
		sales_order.insert()

	# COD orders count as purchases even while the Sales Order stays draft.
	stamp_order_owner(sales_order, shopper)
	log_purchase(sales_order)
	return sales_order


@frappe.whitelist()
def apply_coupon_code(applied_code: str):
	if not applied_code:
		frappe.throw(_("Please enter a coupon code"))
	coupon_name = frappe.db.get_value("Coupon Code", {"coupon_code": applied_code}, "name")
	if not coupon_name:
		frappe.throw(_("Please enter a valid coupon code"))
	validate_coupon_code(coupon_name)
	quotation = _get_cart_quotation()
	validate_cart_is_not_in_checkout(quotation.name)
	quotation.coupon_code = coupon_name
	save_cart_quotation(quotation)
	return {"message": _("Coupon code applied successfully")}


@frappe.whitelist()
def remove_coupon_code():
	quotation = _get_cart_quotation()
	validate_cart_is_not_in_checkout(quotation.name)
	_remove_coupon_code(quotation)


def _remove_coupon_code(quotation):
	quotation.coupon_code = ""
	quotation.items = [item for item in quotation.items if not item.get("is_free_item")]
	for item in quotation.items:
		item.discount_percentage = 0
		item.discount_amount = 0
		item.distributed_discount_amount = 0
		item.rate = item.price_list_rate
	quotation.calculate_taxes_and_totals()
	save_cart_quotation(quotation)
	quotation.discount_amount = 0
	save_cart_quotation(quotation)


def add_billing_address(party_name, address):
	return add_party_address(party_name, address.get("billing_address", {}), "Billing")


def add_shipping_address(party_name, address):
	return add_party_address(party_name, address.get("shipping_address", {}), "Shipping")


def add_party_address(party_name, address: dict, address_type: str):
	if not party_name:
		frappe.throw(_("Cannot save an address without a customer"))

	values = {
		"address_type": address_type,
		"city": address.get("city"),
		"country": address.get("country"),
		"state": address.get("state"),
		"address_line1": address.get("full_address"),
		"address_line2": address.get("landmark"),
		"pincode": address.get("po_box"),
		"phone": address.get("phone_number"),
		"email_id": address.get("email"),
	}
	# A Continue retried after a dropped response must not file the same address twice.
	if existing_address := get_party_address(party_name, values):
		return frappe.get_doc("Address", existing_address)

	address_doc = frappe.get_doc(
		{"doctype": "Address", "address_title": f"Shop {address_type} Address - {party_name}", **values}
	)
	# ERPNext resolves a transaction address through Dynamic Link; unlinked addresses are refused.
	address_doc.append("links", {"link_doctype": "Customer", "link_name": party_name})
	address_doc.insert(ignore_permissions=True)
	return address_doc


def get_party_address(party_name: str, values: dict) -> str | None:
	filters = [
		["Address", field, "=", value] if value else ["Address", field, "is", "not set"]
		for field, value in values.items()
	]
	filters += [
		["Address", "disabled", "=", 0],
		["Dynamic Link", "link_doctype", "=", "Customer"],
		["Dynamic Link", "link_name", "=", party_name],
	]
	matches = frappe.get_all("Address", filters=filters, pluck="name", order_by="creation desc", limit=1)
	return matches[0] if matches else None


def update_quotation_payment_terms_due_date(quotation):
	today = getdate()
	for term in quotation.get("payment_schedule", []):
		if term.due_date and term.due_date < today:
			term.due_date = today


def validate_store_pickup(warehouse: str | None):
	if not frappe.db.get_single_value("Commera Settings", "store_pickup_enabled"):
		frappe.throw(_("Store pickup is not available."))

	# Checkout only lists warehouses that have a Shop address, so one without is not a place to send a shopper.
	if warehouse not in get_pickup_warehouses() or not get_pickup_addresses([warehouse]):
		frappe.throw(_("Please select a valid pickup location."))


def update_delivery_charges(quotation):
	if quotation.custom_is_store_pickup:
		# A cart saved as a pickup before the owner switched pickup off must not reach payment as one.
		validate_store_pickup(quotation.custom_store)
		clear_pickup_charges(quotation)
		save_cart_quotation(quotation)
		return

	# With no option chosen — or bwh_shipping absent — the flat Shipping Rule applies instead.
	if not reprice_selected_option(quotation):
		set_charges(quotation)
	save_cart_quotation(quotation)
