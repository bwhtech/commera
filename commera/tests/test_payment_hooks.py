# Copyright (c) 2026, company@bwhstudios.com and Contributors

import importlib
from unittest.mock import patch

import frappe
from bwh_payments.bwh_payments.doctype.gateway_payment_request.test_gateway_payment_request import (
	GATEWAY,
	configure_stripe_gateway,
	remove_stripe_gateway,
)
from bwh_payments.bwh_payments.doctype.stripe_gateway_settings import stripe_gateway_settings
from bwh_payments.tests.fake_stripe import FakeStripeClient
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, get_year_ending, get_year_start, getdate, now_datetime
from frappe.utils.data import flt

from commera.api.orders import cancel_order
from commera.api.payment_hooks import on_payment_request_update
from commera.api.payments import (
	confirm_payment,
	create_payment_entry,
	get_open_gateway_payment_request,
	make_sales_invoice,
	place_cod_order,
	validate_cart_is_not_in_checkout,
)
from commera.app_events import (
	APPS_USER,
	RETRY_DELAYS_IN_MINUTES,
	fire_event,
	on_sales_order_cancel,
	retry_delivery,
	run_app_deliveries,
	run_due_deliveries,
	sweep_missed_cod_payments,
)
from commera.jobs import sync_pending_gateway_payments
from commera.sdk.events import CommeraEvent

COMPANY = "Lifestyle Demo"
ITEM_GROUP = "Interior Accessories"
DEFAULT_CASH_ACCOUNT = "Cash - LSD"
CURRENCY = "INR"
# A price list in the company currency keeps the fixture off the Currency Exchange table.
PRICE_LIST = "ZZ Payhook SAR Selling"
ITEM_RATE = 150.0


CANCEL_REFUSAL = "Printful is already producing this order."


def refuse_cancel(sales_order, method=None):
	frappe.throw(f"{CANCEL_REFUSAL} ({sales_order.name})")


def record_app_event(event):
	frappe.flags.commera_app_event_calls.append((event, frappe.session.user))


def raise_from_app_event(event):
	raise RuntimeError("an app's broken handler")


def fail_once_then_record(event):
	if not frappe.flags.commera_app_event_failed_once:
		frappe.flags.commera_app_event_failed_once = True
		raise RuntimeError("an app's flaky handler")
	record_app_event(event)


def patch_app_hooks(test_case, app_hooks: dict):
	"""Stand in for an installed app's hooks.py, leaving every other hook (doc_events included) untouched."""
	get_hooks = frappe.get_hooks

	def get_hooks_with_app(hook=None, *args, **kwargs):
		if hook in app_hooks:
			return app_hooks[hook]
		return get_hooks(hook, *args, **kwargs)

	hooks_patch = patch.object(frappe, "get_hooks", side_effect=get_hooks_with_app)
	hooks_patch.start()
	test_case.addCleanup(hooks_patch.stop)


class TestPaymentHookIdempotency(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# get_single hands back a copy older than another class's write, so save() throws TimestampMismatch.
		frappe.clear_cache()
		configure_stripe_gateway()
		cls.ensure_mode_of_payment()
		cls.ensure_price_list()
		cls.ensure_fiscal_year()

	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		# The fixtures run outside the per-test rollback, so a fake-keyed gateway would stay enabled.
		frappe.db.rollback()
		remove_stripe_gateway()
		frappe.delete_doc(
			"Mode of Payment", GATEWAY, ignore_missing=True, ignore_permissions=True, force=True
		)
		frappe.db.commit()

	def setUp(self):
		FakeStripeClient.reset()
		self.addCleanup(frappe.set_user, frappe.session.user)
		# The gateway transport is the only true external boundary here; everything else is real.
		stripe_client_patch = patch.object(stripe_gateway_settings.stripe, "StripeClient", FakeStripeClient)
		stripe_client_patch.start()
		self.addCleanup(stripe_client_patch.stop)

		self.item_code = self.create_item()
		self.customer = self.create_customer()
		self.contact_email = self.create_contact(self.customer)
		self.quotation = self.create_cart_quotation()
		self.payment_request = self.create_paid_payment_request(self.quotation)
		self.shopper = self.create_shopper_user(self.contact_email)

	# -- fixtures ---------------------------------------------------------------------------------

	@classmethod
	def ensure_mode_of_payment(cls):
		"""place_order throws unless a Mode of Payment shares the gateway's exact name."""
		if not frappe.db.exists("Mode of Payment", GATEWAY):
			frappe.get_doc(
				{"doctype": "Mode of Payment", "mode_of_payment": GATEWAY, "enabled": 1, "type": "Bank"}
			).insert(ignore_permissions=True)

		# get_default_bank_cash_account refuses to post a Payment Entry without this row.
		mode_of_payment = frappe.get_doc("Mode of Payment", GATEWAY)
		if not any(row.company == COMPANY for row in mode_of_payment.accounts):
			mode_of_payment.append("accounts", {"company": COMPANY, "default_account": DEFAULT_CASH_ACCOUNT})
			mode_of_payment.save(ignore_permissions=True)

	@classmethod
	def ensure_fiscal_year(cls):
		"""This site was never given one, and every submitted accounting document needs one."""
		year_start = get_year_start(getdate())
		if frappe.db.exists("Fiscal Year", {"year_start_date": year_start, "disabled": 0}):
			return
		frappe.get_doc(
			{
				"doctype": "Fiscal Year",
				"year": str(year_start.year),
				"year_start_date": year_start,
				"year_end_date": get_year_ending(getdate()),
			}
		).insert(ignore_permissions=True, ignore_if_duplicate=True)

	@classmethod
	def ensure_price_list(cls):
		if frappe.db.exists("Price List", PRICE_LIST):
			return
		frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": PRICE_LIST,
				"currency": CURRENCY,
				"selling": 1,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)

	def create_item(self):
		item_code = f"ZZ-PAYHOOK-{frappe.generate_hash(length=8)}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": "ZZ Payment Hook Item",
				"item_group": ITEM_GROUP,
				"stock_uom": "Nos",
				# Non-stock keeps the Sales Invoice off the stock ledger; the hook is what is under test.
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": PRICE_LIST,
				"price_list_rate": ITEM_RATE,
			}
		).insert(ignore_permissions=True)
		return item_code

	def create_customer(self):
		return (
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": f"ZZ Payhook Customer {frappe.generate_hash(length=8)}",
					"customer_type": "Individual",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def create_contact(self, customer):
		email_id = f"zz_payhook_{frappe.generate_hash(length=8)}@example.com"
		contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "ZZ Payhook",
				"email_ids": [{"email_id": email_id, "is_primary": 1}],
				"phone_nos": [{"phone": "+966500000000", "is_primary_phone": 1}],
				"links": [{"link_doctype": "Customer", "link_name": customer}],
			}
		).insert(ignore_permissions=True)
		self.contact_person = contact.name
		return email_id

	def create_cart_quotation(self):
		quotation = frappe.new_doc("Quotation")
		quotation.update(
			{
				"quotation_to": "Customer",
				"party_name": self.customer,
				"company": COMPANY,
				"order_type": "Shopping Cart",
				"contact_person": self.contact_person,
				# The storefront stamps the shopper's login here; ownership checks read it back.
				"contact_email": self.contact_email,
				"currency": CURRENCY,
				"conversion_rate": 1,
				"selling_price_list": PRICE_LIST,
				"price_list_currency": CURRENCY,
				"plc_conversion_rate": 1,
				"items": [{"item_code": self.item_code, "qty": 2}],
			}
		)
		quotation.flags.ignore_permissions = True
		quotation.insert()
		return quotation

	def create_shopper_user(self, email_id):
		"""A real storefront login, so the checkout path can be driven under the shopper's own session."""
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email_id,
				"first_name": "ZZ Payhook Shopper",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}
		)
		user.flags.ignore_permissions = True
		user.insert()
		return user.name

	def create_pending_payment_request(self, quotation, amount=None):
		payment_request = frappe.get_doc(
			{
				"doctype": "Gateway Payment Request",
				"gateway": GATEWAY,
				"amount": quotation.grand_total if amount is None else amount,
				"currency_code": quotation.currency,
				"company": COMPANY,
				"ref_doctype": "Quotation",
				"ref_docname": quotation.name,
				"customer_ref": quotation.party_name,
				"customer_email": self.contact_email,
			}
		).insert(ignore_permissions=True)
		FakeStripeClient.register_paid_session(payment_request.order_ref, CURRENCY.lower())
		return payment_request

	def create_paid_payment_request(self, quotation):
		payment_request = frappe.get_doc(
			{
				"doctype": "Gateway Payment Request",
				"gateway": GATEWAY,
				"amount": quotation.grand_total,
				"currency_code": quotation.currency,
				"company": COMPANY,
				"ref_doctype": "Quotation",
				"ref_docname": quotation.name,
				"customer_ref": quotation.party_name,
				"customer_email": self.contact_email,
			}
		).insert(ignore_permissions=True)

		FakeStripeClient.register_paid_session(
			payment_request.order_ref, payment_request.currency_code.lower()
		)
		# db_set, not save(), so flipping to Paid does not itself fire the hook under test.
		payment_request.db_set("status", "Paid", update_modified=False)
		payment_request.reload()
		return payment_request

	# -- queries ----------------------------------------------------------------------------------

	def submitted_sales_orders(self, quotation_name=None):
		return frappe.get_all(
			"Sales Order Item",
			filters={"prevdoc_docname": quotation_name or self.quotation.name, "docstatus": 1},
			pluck="parent",
			distinct=True,
		)

	def submitted_sales_invoices(self, sales_order):
		return frappe.get_all(
			"Sales Invoice Item",
			filters={"sales_order": sales_order, "docstatus": 1},
			pluck="parent",
			distinct=True,
		)

	def submitted_payment_entries(self, sales_invoice):
		return frappe.get_all(
			"Payment Entry Reference",
			filters={"reference_doctype": "Sales Invoice", "reference_name": sales_invoice, "docstatus": 1},
			pluck="parent",
			distinct=True,
		)

	# -- tests ------------------------------------------------------------------------------------

	def test_a_paid_payment_creates_one_sales_order_and_one_sales_invoice(self):
		on_payment_request_update(self.payment_request)

		sales_orders = self.submitted_sales_orders()
		self.assertEqual(len(sales_orders), 1)
		self.assertEqual(frappe.db.get_value("Quotation", self.quotation.name, "docstatus"), 1)

		sales_invoices = self.submitted_sales_invoices(sales_orders[0])
		self.assertEqual(len(sales_invoices), 1)

		payment_entries = self.submitted_payment_entries(sales_invoices[0])
		self.assertEqual(len(payment_entries), 1)
		self.assertEqual(
			frappe.db.get_value("Payment Entry", payment_entries[0], "reference_no"),
			self.payment_request.order_ref,
		)
		self.assertEqual(frappe.db.get_value("Payment Entry", payment_entries[0], "mode_of_payment"), GATEWAY)

	def test_a_duplicate_callback_does_not_create_a_second_order(self):
		"""A replayed webhook racing a confirm_payment poll must not bill the shopper twice."""
		on_payment_request_update(self.payment_request)
		first_sales_orders = self.submitted_sales_orders()

		# The replay carries the original Quotation reference; only the persisted docstatus can stop it.
		replayed = frappe.get_doc("Gateway Payment Request", self.payment_request.name)
		replayed.ref_doctype = "Quotation"
		replayed.ref_docname = self.quotation.name
		on_payment_request_update(replayed)

		# Without the docstatus guard the replay re-enters place_order, so running it unwrapped asserts it.
		self.assertEqual(self.submitted_sales_orders(), first_sales_orders)
		self.assertEqual(len(self.submitted_sales_orders()), 1)

		sales_invoices = self.submitted_sales_invoices(first_sales_orders[0])
		self.assertEqual(len(sales_invoices), 1)
		self.assertEqual(len(self.submitted_payment_entries(sales_invoices[0])), 1)

		# Any docstatus, so a half-finished replay that only got as far as a draft is still caught.
		self.assertEqual(frappe.db.count("Sales Order", {"customer": self.customer}), 1)
		self.assertEqual(frappe.db.count("Sales Invoice", {"customer": self.customer}), 1)

	def test_saving_the_request_as_paid_fires_the_hook_through_doc_events(self):
		"""Everything else calls the hook directly; this proves the hooks.py wiring reaches it."""
		payment_request = frappe.get_doc(
			{
				"doctype": "Gateway Payment Request",
				"gateway": GATEWAY,
				"amount": self.quotation.grand_total,
				"currency_code": self.quotation.currency,
				"company": COMPANY,
				"ref_doctype": "Quotation",
				"ref_docname": self.quotation.name,
				"customer_ref": self.quotation.party_name,
				"customer_email": self.contact_email,
			}
		).insert(ignore_permissions=True)
		FakeStripeClient.register_paid_session(payment_request.order_ref, CURRENCY.lower())

		payment_request.status = "Paid"
		payment_request.save(ignore_permissions=True)

		self.assertEqual(len(self.submitted_sales_orders()), 1)
		self.assertEqual(payment_request.ref_doctype, "Sales Order")

	# -- refund Payment Entry mirroring ----------------------------------------------------------------

	def create_refund_payment_entry(self, amount, mode_of_payment=GATEWAY):
		"""The outgoing entry a finance user raises to give the shopper their money back."""
		payment_entry = frappe.new_doc("Payment Entry")
		payment_entry.update(
			{
				"payment_type": "Pay",
				"company": COMPANY,
				"party_type": "Customer",
				"party": self.customer,
				"paid_from": DEFAULT_CASH_ACCOUNT,
				"paid_to": frappe.get_cached_value("Company", COMPANY, "default_receivable_account"),
				"paid_amount": amount,
				"received_amount": amount,
				"source_exchange_rate": 1,
				"target_exchange_rate": 1,
				"mode_of_payment": mode_of_payment,
				"reference_no": self.payment_request.order_ref,
				"reference_date": getdate(),
			}
		)
		payment_entry.flags.ignore_permissions = True
		payment_entry.insert()
		payment_entry.submit()
		return payment_entry

	def test_an_amended_refund_payment_entry_does_not_refund_a_second_time(self):
		"""Cancel+amend re-issues the entry as `<name>-1`, which the doc.name dedupe key never matched."""
		on_payment_request_update(self.payment_request)
		FakeStripeClient.created_refunds.clear()

		payment_entry = self.create_refund_payment_entry(50)
		self.assertEqual(len(FakeStripeClient.created_refunds), 1)

		payment_entry.cancel()
		amended = frappe.copy_doc(payment_entry)
		amended.amended_from = payment_entry.name
		amended.docstatus = 0
		amended.flags.ignore_permissions = True
		amended.insert()
		amended.submit()

		self.assertNotEqual(amended.name, payment_entry.name)
		self.assertEqual(len(FakeStripeClient.created_refunds), 1)
		self.assertEqual(
			flt(frappe.db.get_value("Gateway Payment Request", self.payment_request.name, "refund_amount")),
			50.0,
		)

	def test_a_payment_entry_with_no_mode_of_payment_never_reaches_the_gateway(self):
		"""A blank mode plus a coincidentally matching reference_no used to refund real money."""
		on_payment_request_update(self.payment_request)
		FakeStripeClient.created_refunds.clear()

		self.create_refund_payment_entry(50, mode_of_payment=None)

		self.assertEqual(FakeStripeClient.created_refunds, [])
		self.assertEqual(
			flt(frappe.db.get_value("Gateway Payment Request", self.payment_request.name, "refund_amount")),
			0.0,
		)

	# -- the shopper's own session --------------------------------------------------------------------

	def test_a_shopper_confirming_their_own_payment_gets_a_sales_order_and_invoice(self):
		"""confirm_payment is whitelisted, so it runs as the shopper, who holds no accounting roles.

		A missing ignore_account_permission once let get_party_account reject the submit after capture.
		"""
		payment_request = self.create_pending_payment_request(self.quotation)

		frappe.set_user(self.shopper)
		result = confirm_payment(payment_request.name)

		self.assertEqual(result["status"], "Paid")
		sales_orders = self.submitted_sales_orders()
		self.assertEqual(len(sales_orders), 1)
		self.assertEqual(result["order_name"], sales_orders[0])

		sales_invoices = self.submitted_sales_invoices(sales_orders[0])
		self.assertEqual(len(sales_invoices), 1)
		self.assertEqual(len(self.submitted_payment_entries(sales_invoices[0])), 1)

	def test_a_shopper_cannot_confirm_a_payment_that_is_not_theirs(self):
		payment_request = self.create_pending_payment_request(self.quotation)
		intruder = self.create_shopper_user(f"zz_intruder_{frappe.generate_hash(length=8)}@example.com")

		frappe.set_user(intruder)

		with self.assertRaises(frappe.PermissionError):
			confirm_payment(payment_request.name)

		self.assertEqual(self.submitted_sales_orders(), [])

	def test_a_cart_edited_after_the_session_opened_is_refused_not_shipped(self):
		"""ref_docname points at the live draft cart, so the shopper can keep editing it while paying."""
		payment_request = self.create_pending_payment_request(self.quotation)
		charged = payment_request.amount

		self.quotation.items[0].qty = 20
		self.quotation.flags.ignore_permissions = True
		self.quotation.save()
		self.assertGreater(self.quotation.grand_total, charged)

		frappe.set_user(self.shopper)

		with self.assertRaises(frappe.ValidationError):
			confirm_payment(payment_request.name)

		frappe.set_user("Administrator")
		self.assertEqual(self.submitted_sales_orders(), [])
		self.assertEqual(frappe.db.get_value("Quotation", self.quotation.name, "docstatus"), 0)

	def test_a_cod_confirmation_is_refused_while_a_gateway_session_is_open(self):
		"""payment_mode is a query-string parameter, so it is the shopper who chooses this branch."""
		self.create_pending_payment_request(self.quotation)
		frappe.db.set_single_value("Commera Settings", "cod_enabled", 1)

		frappe.set_user(self.shopper)

		with self.assertRaises(frappe.ValidationError):
			confirm_payment(self.quotation.name, payment_mode="COD")

		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Quotation", self.quotation.name, "docstatus"), 0)
		self.assertEqual(frappe.db.count("Sales Order", {"customer": self.customer}), 0)

	def test_the_payment_request_is_repointed_at_the_sales_order(self):
		on_payment_request_update(self.payment_request)

		reference = frappe.db.get_value(
			"Gateway Payment Request",
			self.payment_request.name,
			["ref_doctype", "ref_docname"],
			as_dict=True,
		)
		self.assertEqual(reference.ref_doctype, "Sales Order")
		self.assertEqual(reference.ref_docname, self.submitted_sales_orders()[0])

	def create_abandoned_payment_request(self, quotation):
		payment_request = self.create_pending_payment_request(quotation)
		FakeStripeClient.sessions[payment_request.order_ref].update(
			{"payment_status": "unpaid", "status": "open", "payment_intent": None}
		)
		return payment_request

	def test_an_abandoned_checkout_releases_the_cart_instead_of_refusing_it(self):
		quotation = self.create_cart_quotation()
		payment_request = self.create_abandoned_payment_request(quotation)

		validate_cart_is_not_in_checkout(quotation.name)

		payment_request.reload()
		self.assertEqual(payment_request.status, "Cancelled")
		self.assertEqual(FakeStripeClient.sessions[payment_request.order_ref]["status"], "expired")

	def test_a_cart_whose_payment_the_gateway_still_honours_stays_locked(self):
		quotation = self.create_cart_quotation()
		payment_request = self.create_pending_payment_request(quotation)

		with self.assertRaises(frappe.ValidationError) as raised:
			validate_cart_is_not_in_checkout(quotation.name)

		self.assertIn("already been paid", str(raised.exception))
		payment_request.reload()
		self.assertEqual(payment_request.status, "Paid")

	def test_a_released_cart_is_free_for_every_later_edit(self):
		quotation = self.create_cart_quotation()
		self.create_abandoned_payment_request(quotation)
		validate_cart_is_not_in_checkout(quotation.name)

		validate_cart_is_not_in_checkout(quotation.name)

		self.assertIsNone(get_open_gateway_payment_request(quotation.name))

	def test_a_paid_request_outranks_an_abandoned_one_on_the_same_cart(self):
		paid_request = self.create_paid_payment_request(self.quotation)
		self.create_abandoned_payment_request(self.quotation)

		self.assertEqual(get_open_gateway_payment_request(self.quotation.name), paid_request.name)

	# -- pending payment sweep --------------------------------------------------------------------

	def sweep_pending_gateway_payments(self):
		# The job commits per request, and inside a test that commit would escape the rollback.
		with patch.object(frappe.db, "commit"):
			sync_pending_gateway_payments()

	def age_payment_request(self, payment_request, minutes):
		"""Push a request back past the settle floor, which is what the sweep filters on."""
		frappe.db.set_value(
			"Gateway Payment Request",
			payment_request.name,
			"creation",
			add_to_date(now_datetime(), minutes=-minutes),
			update_modified=False,
		)

	def test_the_sweep_places_an_order_the_shopper_never_came_back_to_confirm(self):
		quotation = self.create_cart_quotation()
		payment_request = self.create_pending_payment_request(quotation)
		self.age_payment_request(payment_request, minutes=30)

		self.sweep_pending_gateway_payments()

		self.assertEqual(
			frappe.db.get_value("Gateway Payment Request", payment_request.name, "status"), "Paid"
		)
		self.assertEqual(frappe.db.get_value("Quotation", quotation.name, "docstatus"), 1)
		self.assertEqual(len(self.submitted_sales_orders(quotation.name)), 1)

	def test_the_sweep_leaves_a_request_too_new_to_have_settled_alone(self):
		"""A shopper still on the gateway's own page reads Pending; touching it buys nothing."""
		quotation = self.create_cart_quotation()
		payment_request = self.create_pending_payment_request(quotation)

		self.sweep_pending_gateway_payments()

		self.assertEqual(
			frappe.db.get_value("Gateway Payment Request", payment_request.name, "status"), "Pending"
		)
		self.assertEqual(self.submitted_sales_orders(quotation.name), [])

	def test_the_sweep_leaves_a_request_older_than_the_lookback_alone(self):
		quotation = self.create_cart_quotation()
		payment_request = self.create_pending_payment_request(quotation)
		self.age_payment_request(payment_request, minutes=60 * 24)

		self.sweep_pending_gateway_payments()

		self.assertEqual(
			frappe.db.get_value("Gateway Payment Request", payment_request.name, "status"), "Pending"
		)

	def test_one_unreachable_gateway_session_does_not_strand_the_rest_of_the_sweep(self):
		unreachable_quotation = self.create_cart_quotation()
		unreachable_request = self.create_pending_payment_request(unreachable_quotation)
		# The fake transport raises for a session it never issued, as an expired reference does.
		frappe.db.set_value("Gateway Payment Request", unreachable_request.name, "order_ref", "cs_test_gone")
		# Strictly older, so the sweep's oldest-first ordering reaches it before the healthy one.
		self.age_payment_request(unreachable_request, minutes=60)

		healthy_quotation = self.create_cart_quotation()
		healthy_request = self.create_pending_payment_request(healthy_quotation)
		self.age_payment_request(healthy_request, minutes=30)

		self.sweep_pending_gateway_payments()

		self.assertEqual(
			frappe.db.get_value("Gateway Payment Request", unreachable_request.name, "status"), "Pending"
		)
		self.assertEqual(
			frappe.db.get_value("Gateway Payment Request", healthy_request.name, "status"), "Paid"
		)
		self.assertEqual(len(self.submitted_sales_orders(healthy_quotation.name)), 1)
		self.assertTrue(
			frappe.db.exists("Error Log", {"reference_name": unreachable_request.name}),
			"the failing request must be logged, not swallowed",
		)

	# -- app events --------------------------------------------------------------------------------

	def app_events(self, sales_order):
		return sorted(
			frappe.get_all(
				"Commera Event",
				{"reference_doctype": "Sales Order", "reference_name": sales_order},
				pluck="event",
			)
		)

	def delivery(self, sales_order, event, app="commera"):
		return frappe.get_all(
			"Commera Event Delivery",
			filters={"parent": f"{sales_order}-{event}", "app": app},
			fields=["name", "status", "attempts", "next_retry_at", "last_error"],
		)[0]

	def queued_app_jobs(self, enqueue):
		return [call.kwargs for call in enqueue.call_args_list if call.args[:1] == (run_app_deliveries,)]

	def record_app_events(self):
		frappe.flags.commera_app_event_calls = []
		self.addCleanup(frappe.flags.pop, "commera_app_event_calls", None)
		return frappe.flags.commera_app_event_calls

	def place_cod_order_for_cart(self):
		frappe.db.set_single_value("Commera Settings", "cod_enabled", 1)
		return place_cod_order(self.quotation.name)

	def test_a_paid_order_queues_placed_then_paid_once_after_commit(self):
		patch_app_hooks(
			self,
			{
				"commera_order_placed": [f"{__name__}.record_app_event"],
				"commera_order_paid": [f"{__name__}.record_app_event"],
			},
		)
		with patch.object(frappe, "enqueue") as enqueue:
			on_payment_request_update(self.payment_request)
			sales_order = self.submitted_sales_orders()[0]
			frappe.local.message_log = []
			fire_event("order_paid", "Sales Order", sales_order)

		self.assertEqual(frappe.local.message_log, [], "a repeat must not pop an error at the user")
		self.assertEqual(self.app_events(sales_order), ["order_paid", "order_placed"])
		job = {
			"app": "commera",
			"reference_doctype": "Sales Order",
			"reference_name": sales_order,
			"lane_event": None,
			"job_id": f"commera-app-events::commera::Sales Order::{sales_order}",
			"deduplicate": True,
			"enqueue_after_commit": True,
		}
		self.assertEqual(self.queued_app_jobs(enqueue), [job, job], "one job per event, none for the repeat")

	def test_an_event_no_app_listens_to_is_recorded_but_queues_nothing(self):
		patch_app_hooks(self, {"commera_order_placed": []})
		with patch.object(frappe, "enqueue") as enqueue:
			sales_order = self.place_cod_order_for_cart()

		self.assertEqual(self.app_events(sales_order.name), ["order_placed"])
		self.assertFalse(
			frappe.db.exists("Commera Event Delivery", {"parent": f"{sales_order.name}-order_placed"})
		)
		self.assertEqual(self.queued_app_jobs(enqueue), [])

	def test_a_cod_order_is_paid_only_once_its_invoice_is_settled(self):
		sales_order = self.place_cod_order_for_cart()
		self.assertEqual(self.app_events(sales_order.name), ["order_placed"])

		sales_order.flags.ignore_permissions = True
		sales_order.submit()
		sales_invoice = make_sales_invoice(sales_order.name, ignore_permissions=True)
		sales_invoice.flags.ignore_permissions = True
		sales_invoice.insert()
		sales_invoice.submit()
		half = flt(sales_invoice.outstanding_amount) / 2

		create_payment_entry(sales_invoice, GATEWAY, half, None)
		self.assertEqual(self.app_events(sales_order.name), ["order_placed"])

		sales_invoice.reload()
		create_payment_entry(sales_invoice, GATEWAY, sales_invoice.outstanding_amount, None)

		self.assertEqual(self.app_events(sales_order.name), ["order_paid", "order_placed"])

	def submit_invoice_for(self, sales_order, qty):
		sales_invoice = make_sales_invoice(sales_order.name, ignore_permissions=True)
		sales_invoice.items[0].qty = qty
		sales_invoice.flags.ignore_permissions = True
		sales_invoice.insert()
		sales_invoice.submit()
		return sales_invoice

	def test_a_cod_order_billed_in_two_invoices_is_paid_only_when_both_are(self):
		sales_order = self.place_cod_order_for_cart()
		sales_order.flags.ignore_permissions = True
		sales_order.submit()
		first_invoice = self.submit_invoice_for(sales_order, qty=1)
		second_invoice = self.submit_invoice_for(sales_order, qty=1)

		create_payment_entry(first_invoice, GATEWAY, first_invoice.outstanding_amount, None)
		self.assertEqual(self.app_events(sales_order.name), ["order_placed"])

		create_payment_entry(second_invoice, GATEWAY, second_invoice.outstanding_amount, None)
		self.assertEqual(self.app_events(sales_order.name), ["order_paid", "order_placed"])

	def test_the_hourly_sweep_fires_paid_for_a_settled_cod_order_the_payment_hook_missed(self):
		patch_app_hooks(self, {"commera_order_paid": []})
		sales_order = self.place_cod_order_for_cart()
		sales_order.flags.ignore_permissions = True
		sales_order.submit()
		sales_invoice = self.submit_invoice_for(sales_order, qty=2)
		with patch("commera.app_events.on_payment_entry_submit"):
			create_payment_entry(sales_invoice, GATEWAY, sales_invoice.outstanding_amount, None)
		self.assertEqual(self.app_events(sales_order.name), ["order_placed"])

		sweep_missed_cod_payments()
		sweep_missed_cod_payments()

		self.assertEqual(self.app_events(sales_order.name), ["order_paid", "order_placed"])

	def test_an_app_before_cancel_refusal_reaches_the_user_without_an_error_log(self):
		doc_events = frappe.get_doc_hooks()
		sales_order_events = doc_events.get("Sales Order", {})
		doc_events_patch = patch.object(
			frappe.local,
			"doc_events_hooks",
			{
				**doc_events,
				"Sales Order": {
					**sales_order_events,
					"before_cancel": [
						*sales_order_events.get("before_cancel", []),
						f"{__name__}.refuse_cancel",
					],
				},
			},
		)
		doc_events_patch.start()
		self.addCleanup(doc_events_patch.stop)
		sales_order = self.place_cod_order_for_cart()
		started_at = now_datetime()

		with self.assertRaises(frappe.ValidationError) as raised:
			cancel_order(sales_order.name)

		self.assertIn(f"{CANCEL_REFUSAL} ({sales_order.name})", str(raised.exception))
		self.assertNotEqual(frappe.db.get_value("Sales Order", sales_order.name, "docstatus"), 2)
		# Error Logs outlive the rollback, and rolled-back order names get reused, so only count this run's.
		self.assertFalse(
			frappe.db.exists(
				"Error Log",
				{"reference_name": sales_order.name, "creation": [">=", started_at]},
			),
			"a refusal is the app's answer, not a failure to log",
		)

	def run_enqueued_jobs_now(self):
		"""Route jobs through the real frappe.enqueue, run inline, so its own keywords can't swallow the job's."""
		enqueue = frappe.enqueue

		def enqueue_now(method, *args, **kwargs):
			kwargs.update(now=True, enqueue_after_commit=False)
			return enqueue(method, *args, **kwargs)

		for enqueue_patch in (
			patch.object(frappe, "enqueue", side_effect=enqueue_now),
			# The job commits per handler; inside a test that would escape the rollback.
			patch.object(frappe.db, "commit"),
			patch.object(frappe.db, "rollback"),
		):
			enqueue_patch.start()
			self.addCleanup(enqueue_patch.stop)

	def add_handler_to_app(self, app: str, handler) -> str:
		"""Stand in for a handler shipped by another installed app; frappe.get_attr refuses unknown apps."""
		attribute = f"commera_test_{handler.__name__}"
		handler_patch = patch.object(importlib.import_module(app), attribute, handler, create=True)
		handler_patch.start()
		self.addCleanup(handler_patch.stop)
		return f"{app}.{attribute}"

	def test_a_cancelled_webshop_order_is_announced_once(self):
		patch_app_hooks(self, {"commera_order_cancelled": [f"{__name__}.record_app_event"]})
		calls = self.record_app_events()
		self.run_enqueued_jobs_now()
		sales_order = self.place_cod_order_for_cart()

		cancel_order(sales_order.name)
		on_sales_order_cancel(frappe.get_doc("Sales Order", sales_order.name))

		self.assertEqual(
			[(event.name, event.sales_order) for event, user in calls],
			[("order_cancelled", sales_order.name)],
		)

	def test_an_installed_app_hears_placed_then_paid_through_the_real_queue(self):
		patch_app_hooks(
			self,
			{
				"commera_order_placed": [f"{__name__}.record_app_event"],
				"commera_order_paid": [f"{__name__}.record_app_event"],
			},
		)
		calls = self.record_app_events()
		self.run_enqueued_jobs_now()

		on_payment_request_update(self.payment_request)

		sales_order = self.submitted_sales_orders()[0]
		self.assertEqual(
			[(event.name, event.sales_order, user) for event, user in calls],
			[("order_placed", sales_order, APPS_USER), ("order_paid", sales_order, APPS_USER)],
		)
		placed = calls[0][0]
		self.assertIsInstance(placed, CommeraEvent)
		self.assertEqual(
			(placed.id, placed.reference_doctype, placed.reference_name),
			(f"{sales_order}-order_placed", "Sales Order", sales_order),
		)
		self.assertEqual(
			placed.data,
			{
				"customer": self.customer,
				"currency": CURRENCY,
				"grand_total": self.quotation.grand_total,
				"payment_mode": GATEWAY,
				"docstatus": 1,
				"shipping_address": None,
			},
		)
		self.assertEqual(placed.created_at, frappe.db.get_value("Commera Event", placed.id, "creation"))
		self.assertEqual(self.delivery(sales_order, "order_placed").status, "Done")
		self.assertEqual(self.delivery(sales_order, "order_paid").status, "Done")

	def test_an_app_never_hears_paid_before_its_placed_handler_succeeds(self):
		patch_app_hooks(
			self,
			{
				"commera_order_placed": [f"{__name__}.fail_once_then_record"],
				"commera_order_paid": [f"{__name__}.record_app_event"],
			},
		)
		calls = self.record_app_events()
		self.addCleanup(frappe.flags.pop, "commera_app_event_failed_once", None)
		self.run_enqueued_jobs_now()

		on_payment_request_update(self.payment_request)

		sales_order = self.submitted_sales_orders()[0]
		placed = self.delivery(sales_order, "order_placed")
		paid = self.delivery(sales_order, "order_paid")
		self.assertEqual(calls, [])
		self.assertEqual((placed.status, placed.attempts), ("Queued", 1))
		self.assertEqual((paid.status, paid.attempts), ("Queued", 0))

		with self.freeze_time(placed.next_retry_at):
			run_due_deliveries()

		# A gateway call commits mid-checkout, so earlier tests can leave due deliveries the sweep also runs.
		self.assertEqual(
			[event.name for event, user in calls if event.sales_order == sales_order],
			["order_placed", "order_paid"],
		)

	def test_a_failing_app_is_retried_on_schedule_then_failed_without_holding_up_another(self):
		broken_handler = self.add_handler_to_app("bwh_payments", raise_from_app_event)
		patch_app_hooks(self, {"commera_order_placed": [broken_handler, f"{__name__}.record_app_event"]})
		calls = self.record_app_events()
		self.run_enqueued_jobs_now()

		placed_at = now_datetime()
		sales_order = self.place_cod_order_for_cart().name
		broken = self.delivery(sales_order, "order_placed", app="bwh_payments")
		self.assertEqual(broken.attempts, 1)
		self.assertGreaterEqual(
			broken.next_retry_at, add_to_date(placed_at, minutes=RETRY_DELAYS_IN_MINUTES[0])
		)
		self.assertLessEqual(
			broken.next_retry_at, add_to_date(now_datetime(), minutes=RETRY_DELAYS_IN_MINUTES[0])
		)

		with self.freeze_time(add_to_date(broken.next_retry_at, seconds=-1)):
			run_due_deliveries()
		self.assertEqual(
			self.delivery(sales_order, "order_placed", app="bwh_payments").attempts, 1, "not due yet"
		)

		for delay in RETRY_DELAYS_IN_MINUTES[1:]:
			retried_at = broken.next_retry_at
			with self.freeze_time(retried_at):
				run_due_deliveries()
			broken = self.delivery(sales_order, "order_placed", app="bwh_payments")
			self.assertEqual(
				(broken.status, broken.next_retry_at), ("Queued", add_to_date(retried_at, minutes=delay))
			)

		with self.freeze_time(broken.next_retry_at):
			run_due_deliveries()

		broken = self.delivery(sales_order, "order_placed", app="bwh_payments")
		self.assertEqual((broken.status, broken.attempts, broken.next_retry_at), ("Failed", 6, None))
		self.assertEqual(frappe.db.get_value("Error Log", broken.last_error, "reference_name"), sales_order)
		self.assertEqual(self.delivery(sales_order, "order_placed").status, "Done")
		self.assertEqual(
			len([event for event, user in calls if event.sales_order == sales_order]),
			1,
			"the healthy app ran once and was never retried",
		)

	def test_a_failed_delivery_runs_again_when_staff_retry_it(self):
		self.add_handler_to_app("bwh_payments", raise_from_app_event)
		handler = self.add_handler_to_app("bwh_payments", record_app_event)
		patch_app_hooks(self, {"commera_order_placed": ["bwh_payments.commera_test_raise_from_app_event"]})
		calls = self.record_app_events()
		self.run_enqueued_jobs_now()
		sales_order = self.place_cod_order_for_cart().name
		failed = self.delivery(sales_order, "order_placed", app="bwh_payments")
		frappe.db.set_value("Commera Event Delivery", failed.name, {"status": "Failed", "attempts": 6})
		frappe.db.set_value("Commera Event Delivery", failed.name, "handler", handler)

		frappe.set_user(self.shopper)
		with self.assertRaises(frappe.PermissionError):
			retry_delivery(failed.name)
		frappe.set_user("Administrator")
		retry_delivery(failed.name)

		retried = self.delivery(sales_order, "order_placed", app="bwh_payments")
		self.assertEqual((retried.status, retried.attempts), ("Done", 7))
		self.assertEqual([event.id for event, user in calls], [f"{sales_order}-order_placed"])
