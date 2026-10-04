# Copyright (c) 2026, company@bwhstudios.com and Contributors

import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate
from rq.job import JobStatus

from commera.api.admin.catalog import (
	create_product,
	save_product_options,
	save_product_prices,
	set_variant_price,
	set_variant_published,
)
from commera.api.orders import cancel_order, make_refund_payment_entry
from commera.api.payment_hooks import on_payment_request_update
from commera.api.payments import create_payment_entry
from commera.app_events import (
	APPS_USER,
	STALE_CLAIM_MINUTES,
	add_apps_user,
	enqueue_app_deliveries,
	fire_event,
	fire_inventory_changed,
	on_payment_entry_submit,
	reset_changed_products,
	run_app_deliveries,
	run_due_deliveries,
	run_lane,
	validate_extension_apps,
)
from commera.commera_ecommerce.doctype.bulk_publish_variants.bulk_publish_variants import (
	set_variants_published,
)
from commera.commera_ecommerce.doctype.commera_event.commera_event import CommeraEvent
from commera.sdk import API_VERSION
from commera.tests import test_admin_catalog
from commera.tests import test_payment_hooks as payment_hooks
from commera.tests.test_admin_orders import make_test_sales_order
from commera.tests.test_payment_hooks import COMPANY, CURRENCY, ITEM_GROUP, patch_app_hooks
from commera.tests.test_product_onboarding import ProductOnboardingTestCase
from commera.utils import update_sales_order_ecommerce_status

try:
	from erpnext.accounts.doctype.sales_invoice.mapper import make_sales_return
	from erpnext.selling.doctype.sales_order.mapper import make_delivery_note
	from erpnext.stock.doctype.delivery_note.mapper import make_sales_return as make_delivery_return
except ImportError:
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_return as make_delivery_return

RECORD_APP_EVENT = f"{payment_hooks.__name__}.record_app_event"
STORE_WAREHOUSE = "Stores - LSD"
OTHER_WAREHOUSE = "Finished Goods - LSD"


def start_recording_product_changes():
	"""Forget what the fixtures changed, and the after-commit callbacks earlier tests left queued."""
	frappe.db.after_commit.reset()
	reset_changed_products()


def patch_app_declarations(test_case, hooks_by_app: dict):
	"""Stand in for what each named app's own hooks.py declares, as read with frappe.get_hooks(app_name=...)."""
	get_hooks = frappe.get_hooks

	def get_hooks_for_app(hook=None, *args, app_name=None, **kwargs):
		if app_name in hooks_by_app:
			app_hooks = hooks_by_app[app_name]
			return app_hooks.get(hook, []) if hook else frappe._dict(app_hooks)
		return get_hooks(hook, *args, app_name=app_name, **kwargs)

	hooks_patch = patch.object(frappe, "get_hooks", side_effect=get_hooks_for_app)
	hooks_patch.start()
	test_case.addCleanup(hooks_patch.stop)


class TestAppEvents(payment_hooks.TestPaymentHookIdempotency):
	def commera_events(self, reference_name, event):
		return frappe.get_all(
			"Commera Event",
			filters={"reference_name": reference_name, "event": event},
			fields=["name", "data"],
			order_by="creation asc",
		)

	def event_names(self, reference_name):
		return sorted(frappe.get_all("Commera Event", {"reference_name": reference_name}, pluck="event"))

	def book_parcel(self, sales_order, status):
		parcel = frappe.get_doc(
			{
				"doctype": "Shipping Request",
				"name": frappe.generate_hash(length=10),
				"ref_doctype": "Sales Order",
				"ref_docname": sales_order,
				"status": status,
			}
		)
		parcel.db_insert()
		return parcel.name

	def submitted_cod_order(self):
		sales_order = self.place_cod_order_for_cart()
		sales_order.flags.ignore_permissions = True
		sales_order.submit()
		return sales_order.name

	def test_an_order_is_announced_fulfilled_then_delivered_once_each(self):
		patch_app_hooks(self, {"commera_events": {"order_fulfilled": [], "order_delivered": []}})
		sales_order = self.submitted_cod_order()
		update_sales_order_ecommerce_status(sales_order)
		parcel = self.book_parcel(sales_order, "Ready To Ship")
		update_sales_order_ecommerce_status(sales_order)
		self.assertEqual(self.event_names(sales_order), ["order_placed"])

		frappe.db.set_value("Shipping Request", parcel, "status", "In Transit")
		update_sales_order_ecommerce_status(sales_order)
		frappe.db.set_value("Shipping Request", parcel, "status", "Out For Delivery")
		update_sales_order_ecommerce_status(sales_order)
		self.assertEqual(self.event_names(sales_order), ["order_fulfilled", "order_placed"])

		frappe.db.set_value("Shipping Request", parcel, "status", "Delivered")
		update_sales_order_ecommerce_status(sales_order)
		update_sales_order_ecommerce_status(sales_order)

		self.assertEqual(
			frappe.db.get_value("Sales Order", sales_order, "custom_ecommerce_status"), "Delivered"
		)
		self.assertEqual(
			self.event_names(sales_order), ["order_delivered", "order_fulfilled", "order_placed"]
		)

	def test_an_order_shipped_without_a_carrier_is_announced_fulfilled_then_delivered(self):
		patch_app_hooks(
			self,
			{
				"commera_events": {
					"order_fulfilled": [RECORD_APP_EVENT],
					"order_delivered": [RECORD_APP_EVENT],
				}
			},
		)
		calls = self.record_app_events()
		self.run_enqueued_jobs_now()
		sales_order = self.submitted_cod_order()
		delivery_note = make_delivery_note(sales_order)
		delivery_note.flags.ignore_permissions = True
		delivery_note.insert()
		delivery_note.submit()

		update_sales_order_ecommerce_status(sales_order)

		self.assertEqual(
			[(event.name, event.sales_order) for event, user in calls],
			[("order_fulfilled", sales_order), ("order_delivered", sales_order)],
		)

	def test_an_order_placed_outside_the_store_is_never_announced(self):
		sales_order = make_test_sales_order().name
		parcel = self.book_parcel(sales_order, "Delivered")

		update_sales_order_ecommerce_status(sales_order)
		frappe.db.set_value("Shipping Request", parcel, "status", "RTO")
		update_sales_order_ecommerce_status(sales_order)

		self.assertEqual(
			frappe.db.get_value("Sales Order", sales_order, "custom_ecommerce_status"), "Returned"
		)
		self.assertEqual(self.event_names(sales_order), [])

	def submit_delivery_note(self, sales_order):
		delivery_note = make_delivery_note(sales_order)
		delivery_note.flags.ignore_permissions = True
		delivery_note.insert()
		delivery_note.submit()
		return delivery_note.name

	def submit_delivery_return(self, delivery_note, returned_qty):
		return_note = make_delivery_return(delivery_note)
		return_note.items[0].qty = -returned_qty
		return_note.flags.ignore_permissions = True
		return_note.insert()
		return_note.submit()

	def returns_announced(self, sales_order):
		return [
			(event.name, frappe.parse_json(event.data).status, frappe.parse_json(event.data).partial)
			for event in self.commera_events(sales_order, "order_returned")
		]

	def test_a_partial_then_a_full_return_are_announced_once_each(self):
		patch_app_hooks(self, {"commera_events": {"order_returned": []}})
		sales_order = self.submitted_cod_order()
		delivery_note = self.submit_delivery_note(sales_order)
		update_sales_order_ecommerce_status(sales_order)

		self.submit_delivery_return(delivery_note, 1)
		update_sales_order_ecommerce_status(sales_order)
		update_sales_order_ecommerce_status(sales_order)
		self.submit_delivery_return(delivery_note, 1)
		update_sales_order_ecommerce_status(sales_order)
		update_sales_order_ecommerce_status(sales_order)

		self.assertEqual(
			frappe.db.get_value("Sales Order", sales_order, "custom_ecommerce_status"), "Returned"
		)
		self.assertEqual(
			self.returns_announced(sales_order),
			[
				(f"{sales_order}-order_returned-partially_returned", "Partially Returned", True),
				(f"{sales_order}-order_returned-returned", "Returned", False),
			],
		)
		self.assertEqual(
			self.event_names(sales_order),
			["order_delivered", "order_fulfilled", "order_placed", "order_returned", "order_returned"],
		)

	def test_a_parcel_returned_to_origin_is_announced_fulfilled_then_returned(self):
		patch_app_hooks(
			self,
			{"commera_events": {"order_fulfilled": [RECORD_APP_EVENT], "order_returned": [RECORD_APP_EVENT]}},
		)
		calls = self.record_app_events()
		self.run_enqueued_jobs_now()
		sales_order = self.submitted_cod_order()
		self.book_parcel(sales_order, "RTO")

		update_sales_order_ecommerce_status(sales_order)

		self.assertEqual(
			[(event.name, event.data.get("partial")) for event, user in calls],
			[("order_fulfilled", None), ("order_returned", False)],
		)

	def test_each_refund_is_announced_once_with_its_payment_entry(self):
		patch_app_hooks(self, {"commera_events": {"order_refunded": []}})
		on_payment_request_update(self.payment_request)
		sales_order = self.submitted_sales_orders()[0]

		store_refund = make_refund_payment_entry(sales_order, 50)
		desk_refund = self.create_refund_payment_entry(30)
		on_payment_entry_submit(desk_refund)

		self.assertEqual(
			self.refunds_announced(sales_order),
			[
				(store_refund, 50.0, CURRENCY, self.customer),
				(desk_refund.name, 30.0, CURRENCY, self.customer),
			],
		)

	def refunds_announced(self, sales_order):
		refunds = []
		for event in self.commera_events(sales_order, "order_refunded"):
			data = frappe.parse_json(event.data)
			self.assertEqual(event.name, f"{sales_order}-order_refunded-{data.payment_entry}")
			refunds.append((data.payment_entry, data.amount, data.currency, data.customer))
		return refunds

	def test_the_refund_a_cancel_pays_out_is_announced(self):
		patch_app_hooks(self, {"commera_events": {"order_refunded": []}})
		on_payment_request_update(self.payment_request)
		sales_order = self.submitted_sales_orders()[0]
		frappe.set_user(frappe.db.get_value("Sales Order", sales_order, "owner"))

		cancel_order(sales_order)

		frappe.set_user("Administrator")
		(refund,) = self.refunds_announced(sales_order)
		self.assertEqual(refund[1:], (self.payment_request.amount, CURRENCY, self.customer))

	def submit_credit_note(self, sales_order, returned_qty):
		sales_invoice = self.submit_invoice_for(frappe.get_doc("Sales Order", sales_order), qty=2)
		create_payment_entry(sales_invoice, payment_hooks.GATEWAY, sales_invoice.outstanding_amount, None)
		credit_note = make_sales_return(sales_invoice.name)
		credit_note.items[0].qty = -returned_qty
		credit_note.flags.ignore_permissions = True
		credit_note.insert()
		credit_note.submit()
		return credit_note

	def test_a_cod_refund_made_in_desk_is_announced_through_its_credit_note(self):
		patch_app_hooks(self, {"commera_events": {"order_refunded": []}})
		sales_order = self.submitted_cod_order()
		credit_note = self.submit_credit_note(sales_order, returned_qty=1)

		refund = get_payment_entry("Sales Invoice", credit_note.name)
		# Cash, so no reference number: only the credit note can tie this refund to the order.
		refund.update(
			{"paid_from": payment_hooks.DEFAULT_CASH_ACCOUNT, "mode_of_payment": None, "reference_no": None}
		)
		refund.flags.ignore_permissions = True
		refund.insert()
		refund.submit()

		self.assertEqual(
			self.refunds_announced(sales_order), [(refund.name, refund.paid_amount, CURRENCY, self.customer)]
		)

	def test_one_desk_refund_for_two_orders_announces_each_order_its_own_share(self):
		patch_app_hooks(self, {"commera_events": {"order_refunded": []}})
		first_order = self.submitted_cod_order()
		self.quotation = self.create_cart_quotation()
		second_order = self.submitted_cod_order()
		first_note = self.submit_credit_note(first_order, returned_qty=1)
		second_note = self.submit_credit_note(second_order, returned_qty=2)

		refund = get_payment_entry("Sales Invoice", first_note.name)
		second_reference = get_payment_entry("Sales Invoice", second_note.name).references[0]
		refund.append(
			"references",
			{
				field: second_reference.get(field)
				for field in (
					"reference_doctype",
					"reference_name",
					"due_date",
					"total_amount",
					"outstanding_amount",
					"allocated_amount",
				)
			},
		)
		refund_total = abs(first_note.grand_total) + abs(second_note.grand_total)
		refund.update(
			{
				"paid_from": payment_hooks.DEFAULT_CASH_ACCOUNT,
				"mode_of_payment": None,
				"reference_no": None,
				"paid_amount": refund_total,
				"received_amount": refund_total,
			}
		)
		refund.flags.ignore_permissions = True
		refund.insert()
		refund.submit()

		self.assertEqual(
			self.refunds_announced(first_order),
			[(refund.name, abs(first_note.grand_total), CURRENCY, self.customer)],
		)
		self.assertEqual(
			self.refunds_announced(second_order),
			[(refund.name, abs(second_note.grand_total), CURRENCY, self.customer)],
		)

	def test_an_item_code_as_long_as_the_limit_still_records_its_events(self):
		item_code = f"ZZ-LONG-{frappe.generate_hash(length=8)}".ljust(130, "X")
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": "ZZ Long Item",
				"item_group": ITEM_GROUP,
				"stock_uom": "Nos",
			}
		).insert(ignore_permissions=True)
		patch_app_hooks(self, {"commera_events": {"product_updated": [RECORD_APP_EVENT]}})

		with patch.object(frappe, "enqueue"):
			fire_event("product_updated", "Item", item_code, key=frappe.generate_hash(length=10))

		self.assertEqual(len(self.commera_events(item_code, "product_updated")), 1)

	def create_listed_item(self):
		return self.list_item(self.create_item())

	def list_item(self, item_code):
		variant = frappe.get_doc(
			{
				"doctype": "Style Attribute Variant",
				"name": f"ZZ-EVENTS-{frappe.generate_hash(length=8)}",
				"item_style": item_code,
				"attribute_value": "Red",
				"display_name": "ZZ Events Variant",
				"is_published": 1,
			}
		)
		variant.db_insert()
		frappe.get_doc(
			{
				"doctype": "Color Size Item",
				"name": frappe.generate_hash(length=10),
				"parent": variant.name,
				"parenttype": "Style Attribute Variant",
				"parentfield": "sizes",
				"size": "S",
				"item_code": item_code,
			}
		).db_insert()
		return item_code

	def save_item(self, item_code):
		item = frappe.get_doc("Item", item_code)
		item.description = frappe.generate_hash(length=10)
		item.save(ignore_permissions=True)

	def test_two_saves_of_a_listed_item_are_announced_once_after_commit(self):
		patch_app_hooks(self, {"commera_events": {"product_updated": [RECORD_APP_EVENT]}})
		calls = self.record_app_events()
		self.run_enqueued_jobs_now()
		listed_item = self.create_listed_item()
		unlisted_item = self.create_item()
		start_recording_product_changes()

		self.save_item(listed_item)
		self.save_item(listed_item)
		self.save_item(unlisted_item)
		self.assertEqual(calls, [], "nothing is announced before the save commits")
		frappe.db.after_commit.run()

		self.assertEqual(
			[(event.reference_name, event.data) for event, user in calls],
			[(listed_item, {"item_code": listed_item, "changed": ["details"]})],
		)

	def test_a_product_event_no_app_listens_to_is_not_recorded(self):
		patch_app_hooks(self, {"commera_events": {"product_updated": [], "inventory_changed": []}})
		listed_item = self.create_listed_item()

		self.save_item(listed_item)
		fire_inventory_changed(listed_item)

		self.assertEqual(self.event_names(listed_item), [])

	def create_stock_item(self):
		item_code = f"ZZ-EVENTS-STOCK-{frappe.generate_hash(length=8)}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": "ZZ Events Stock Item",
				"item_group": ITEM_GROUP,
				"stock_uom": "Nos",
				"is_stock_item": 1,
			}
		).insert(ignore_permissions=True)
		return item_code

	def receive_stock(self, rows):
		stock_entry = frappe.new_doc("Stock Entry")
		stock_entry.update(
			{
				"stock_entry_type": "Material Receipt",
				"company": COMPANY,
				"items": [
					{"item_code": item_code, "qty": qty, "t_warehouse": warehouse, "basic_rate": 10}
					for item_code, qty, warehouse in rows
				],
			}
		)
		stock_entry.flags.ignore_permissions = True
		stock_entry.insert()
		stock_entry.submit()

	def test_a_stock_entry_announces_each_store_item_once_with_its_new_qty(self):
		patch_app_hooks(self, {"commera_events": {"inventory_changed": [RECORD_APP_EVENT]}})
		# Commera Settings is shared with suites running in parallel on this site.
		warehouse_patch = patch("commera.app_events.get_ecommerce_warehouse", return_value=STORE_WAREHOUSE)
		warehouse_patch.start()
		self.addCleanup(warehouse_patch.stop)
		calls = self.record_app_events()
		self.run_enqueued_jobs_now()
		shirt, cap = self.list_item(self.create_stock_item()), self.list_item(self.create_stock_item())
		unlisted, elsewhere = self.create_stock_item(), self.list_item(self.create_stock_item())
		# Nothing commits inside the class, so earlier tests' after-commit callbacks are still queued.
		frappe.db.after_commit.reset()

		self.receive_stock(
			[
				(shirt, 2, STORE_WAREHOUSE),
				(shirt, 3, STORE_WAREHOUSE),
				(cap, 4, STORE_WAREHOUSE),
				(unlisted, 1, STORE_WAREHOUSE),
				(elsewhere, 6, OTHER_WAREHOUSE),
			]
		)
		self.assertEqual(calls, [], "nothing is announced before the stock entry commits")
		frappe.db.after_commit.run()

		self.assertEqual(
			sorted((event.reference_name, event.data) for event, user in calls),
			sorted(
				[
					(shirt, {"warehouse": STORE_WAREHOUSE, "actual_qty": 5.0, "available_qty": 5.0}),
					(cap, {"warehouse": STORE_WAREHOUSE, "actual_qty": 4.0, "available_qty": 4.0}),
				]
			),
		)

	def test_reserving_and_releasing_stock_for_an_order_is_announced(self):
		patch_app_hooks(self, {"commera_events": {"inventory_changed": [RECORD_APP_EVENT]}})
		warehouse_patch = patch("commera.app_events.get_ecommerce_warehouse", return_value=STORE_WAREHOUSE)
		warehouse_patch.start()
		self.addCleanup(warehouse_patch.stop)
		calls = self.record_app_events()
		self.run_enqueued_jobs_now()
		shirt = self.list_item(self.create_stock_item())
		sales_order = frappe.new_doc("Sales Order")
		sales_order.update(
			{
				"customer": self.customer,
				"company": COMPANY,
				"delivery_date": add_days(nowdate(), 3),
				"items": [{"item_code": shirt, "qty": 2, "rate": 10, "warehouse": STORE_WAREHOUSE}],
			}
		)
		sales_order.flags.ignore_permissions = True
		sales_order.insert()
		frappe.db.after_commit.reset()
		self.receive_stock([(shirt, 5, STORE_WAREHOUSE)])
		frappe.db.after_commit.run()
		# The inline job leaves the session on the apps user, who can't read the order's accounts.
		frappe.set_user("Administrator")
		calls.clear()

		sales_order.submit()
		frappe.db.after_commit.run()
		frappe.set_user("Administrator")
		sales_order.reload()
		sales_order.cancel()
		frappe.db.after_commit.run()

		self.assertEqual(
			[(event.reference_name, event.data["available_qty"]) for event, user in calls],
			[(shirt, 3.0), (shirt, 5.0)],
		)

	def test_an_app_built_for_another_api_version_is_skipped_and_logged(self):
		outdated_handler = self.add_handler_to_app("bwh_payments", payment_hooks.record_app_event)
		current_handler = self.add_handler_to_app("bwh_shipping", payment_hooks.record_app_event)
		patch_app_hooks(self, {"commera_events": {"product_updated": [outdated_handler, current_handler]}})
		patch_app_declarations(
			self,
			{
				"bwh_payments": {
					"commera_api_version": [99],
					"commera_events": {"product_updated": [outdated_handler]},
				},
				"bwh_shipping": {"commera_events": {"product_updated": [current_handler]}},
			},
		)
		started_at = now_datetime()

		with patch.object(frappe, "enqueue"):
			fire_event("product_updated", "Item", self.item_code, key="compat")
		with redirect_stdout(StringIO()) as output:
			validate_extension_apps()

		self.assertEqual(
			frappe.get_all(
				"Commera Event Delivery",
				{"parent": "product_updated-compat"},
				pluck="handler",
			),
			[current_handler],
		)
		self.assertIn("bwh_shipping doesn't declare commera_api_version", output.getvalue())
		self.assertTrue(
			frappe.db.exists(
				"Error Log",
				{"method": "bwh_payments does not support this Commera", "creation": [">=", started_at]},
			)
		)

	def test_each_apps_handlers_for_an_event_are_delivered_in_app_order(self):
		app_declarations = {
			"bwh_payments": {
				"commera_api_version": [99],
				"commera_events": {"product_updated": ["bwh_payments.on_product"]},
			},
			"bwh_shipping": {
				"commera_api_version": [API_VERSION],
				"commera_events": {
					"product_updated": "bwh_shipping.on_product",
					"inventory_changed": ["bwh_shipping.on_stock"],
				},
			},
			"commera": {"commera_events": {"product_updated": ["commera.on_product"]}},
		}
		# The same merge frappe.get_hooks applies to every installed app's hooks.py.
		merged_hooks = {}
		for declarations in app_declarations.values():
			frappe.append_hook(merged_hooks, "commera_events", declarations["commera_events"])
		patch_app_hooks(self, merged_hooks)
		patch_app_declarations(self, {app: app_declarations[app] for app in ("bwh_payments", "bwh_shipping")})

		with patch.object(frappe, "enqueue"):
			fire_event("product_updated", "Item", self.item_code, key="merged")

		self.assertEqual(
			frappe.get_all(
				"Commera Event Delivery",
				{"parent": "product_updated-merged"},
				pluck="handler",
				order_by="idx asc",
			),
			["bwh_shipping.on_product", "commera.on_product"],
		)

	def test_an_event_or_checkout_name_commera_does_not_know_is_warned_about(self):
		patch_app_declarations(
			self,
			{
				"bwh_payments": {
					"commera_api_version": [API_VERSION],
					"commera_events": {
						"order_payed": ["bwh_payments.paid"],
						"order_paid": ["bwh_payments.paid"],
					},
				},
				"bwh_shipping": {"commera_checkout": {"cart_fee": ["bwh_shipping.fees"]}},
			},
		)
		started_at = now_datetime()

		with redirect_stdout(StringIO()) as output:
			validate_extension_apps()

		self.assertIn("bwh_payments declares commera_events for order_payed, which", output.getvalue())
		self.assertIn("bwh_shipping declares commera_checkout for cart_fee, which", output.getvalue())
		self.assertNotIn("bwh_payments declares commera_checkout", output.getvalue())
		self.assertTrue(
			frappe.db.exists(
				"Error Log",
				{"method": "bwh_payments declares unknown commera_events", "creation": [">=", started_at]},
			)
		)

	def add_custom_field(self, dt, fieldname, module):
		frappe.get_doc(
			{
				"doctype": "Custom Field",
				"name": f"{dt}-{fieldname}",
				"dt": dt,
				"fieldname": fieldname,
				"fieldtype": "Data",
				"module": module,
			}
		).db_insert()

	def test_custom_fields_an_app_adds_without_its_prefix_are_listed(self):
		patch_app_declarations(
			self,
			{
				"bwh_payments": {
					"commera_api_version": [1],
					"commera_events": {"order_paid": ["bwh_payments.paid"]},
				}
			},
		)
		# db_insert, not insert: a real Custom Field alters the table, and the DDL would commit the test.
		self.add_custom_field("Item", "zz_gift_wrap", "BWH Payments")
		self.add_custom_field("Item", "bwh_payments_zz_gift_note", "BWH Payments")
		self.add_custom_field("Customer", "zz_loyalty_tier", "Commera Ecommerce")

		with redirect_stdout(StringIO()) as output:
			validate_extension_apps()

		self.assertIn("Item.zz_gift_wrap (bwh_payments)", output.getvalue())
		self.assertNotIn("bwh_payments_zz_gift_note", output.getvalue())
		self.assertNotIn("zz_loyalty_tier", output.getvalue())

	def test_a_failing_product_handler_never_holds_up_the_same_items_stock_updates(self):
		broken_handler = self.add_handler_to_app("bwh_payments", payment_hooks.raise_from_app_event)
		stock_handler = self.add_handler_to_app("bwh_payments", payment_hooks.record_app_event)
		patch_app_hooks(
			self,
			{"commera_events": {"product_updated": [broken_handler], "inventory_changed": [stock_handler]}},
		)
		calls = self.record_app_events()
		self.run_enqueued_jobs_now()

		fire_event("product_updated", "Item", self.item_code, key="first")
		fire_event("inventory_changed", "Item", self.item_code, key="second")

		self.assertEqual([event.id for event, user in calls], ["inventory_changed-second"])
		self.assertEqual(
			frappe.db.get_value("Commera Event Delivery", {"parent": "product_updated-first"}, "attempts"),
			1,
		)

	def add_event(self, event, status, days_old):
		event_key = f"{self.item_code}-{event}-{frappe.generate_hash(length=6)}"
		frappe.get_doc(
			{
				"doctype": "Commera Event",
				"event": event,
				"reference_doctype": "Item",
				"reference_name": self.item_code,
				"event_key": event_key,
				"deliveries": [{"app": "bwh_payments", "handler": "bwh_payments.handler", "status": status}],
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Commera Event", event_key, "creation", add_days(now_datetime(), -days_old))
		return event_key

	def test_the_apps_user_can_book_accounts_but_is_not_a_shopper(self):
		add_apps_user()

		roles = frappe.get_roles(APPS_USER)
		self.assertIn("Accounts Manager", roles)
		self.assertNotIn("Customer", roles)
		self.assertTrue(frappe.has_permission("Account", "read", user=APPS_USER))

	def test_old_item_events_are_cleared_but_order_events_and_unsent_ones_are_kept(self):
		old_product_update = self.add_event("product_updated", "Done", days_old=15)
		old_stock_update = self.add_event("inventory_changed", "Failed", days_old=15)
		unsent_stock_update = self.add_event("inventory_changed", "Queued", days_old=15)
		recent_product_update = self.add_event("product_updated", "Done", days_old=13)
		old_order_event = self.add_event("order_placed", "Done", days_old=400)

		CommeraEvent.clear_old_logs(days=14)

		kept = set(frappe.get_all("Commera Event", {"reference_name": self.item_code}, pluck="name"))
		self.assertEqual(kept, {unsent_stock_update, recent_product_update, old_order_event})
		self.assertFalse(
			frappe.db.exists(
				"Commera Event Delivery", {"parent": ["in", [old_product_update, old_stock_update]]}
			)
		)


# Subclassed only for its checkout fixtures: its own tests already run in test_payment_hooks.
for test_name in unittest.defaultTestLoader.getTestCaseNames(payment_hooks.TestPaymentHookIdempotency):
	setattr(TestAppEvents, test_name, None)


def reenter_own_lane(event):
	frappe.flags.commera_claim_calls.append(event.id)
	if len(frappe.flags.commera_claim_calls) == 1:
		run_lane("commera", event.reference_doctype, event.reference_name, event.name)


def commit_inside_handler(event):
	frappe.flags.commera_claim_calls.append(event.id)
	frappe.db.commit()


class TestAppEventDeliveryClaims(IntegrationTestCase):
	"""Real commits, unlike the suites above: a claim is only worth testing across the handler's own commit.
	Events reference the Company, so committing one never commits a fixture document with it."""

	def setUp(self):
		frappe.flags.commera_claim_calls = []
		self.addCleanup(frappe.flags.pop, "commera_claim_calls", None)
		enqueue_patch = patch.object(frappe, "enqueue")
		self.enqueue = enqueue_patch.start()
		self.addCleanup(enqueue_patch.stop)
		self.event = f"zz_claim_{frappe.generate_hash(length=6)}"

	def fire_committed_event(self, handler) -> str:
		patch_app_hooks(self, {"commera_events": {self.event: [f"{__name__}.{handler.__name__}"]}})
		key = frappe.generate_hash(length=10)
		fire_event(self.event, "Company", COMPANY, key=key)
		event_key = f"{self.event}-{key}"
		self.addCleanup(self.delete_event, event_key)
		frappe.db.commit()
		return event_key

	def delete_event(self, event_key):
		frappe.db.rollback()
		frappe.db.delete("Commera Event Delivery", {"parent": event_key})
		frappe.db.delete("Commera Event", {"name": event_key})
		frappe.db.commit()

	def delivery(self, event_key):
		return frappe.db.get_value(
			"Commera Event Delivery", {"parent": event_key}, ["status", "attempts"], as_dict=True
		)

	def test_a_handler_that_reenters_its_own_lane_runs_once(self):
		event_key = self.fire_committed_event(reenter_own_lane)

		run_app_deliveries("commera", "Company", COMPANY, self.event)

		self.assertEqual(frappe.flags.commera_claim_calls, [event_key])
		self.assertEqual(self.delivery(event_key), {"status": "Done", "attempts": 1})

	def test_an_uninstalled_apps_deliveries_fail_at_once_instead_of_retrying(self):
		event_key = self.fire_committed_event(commit_inside_handler)
		frappe.db.set_value("Commera Event Delivery", {"parent": event_key}, "app", "app_that_was_removed")
		frappe.db.commit()

		run_app_deliveries("app_that_was_removed", "Company", COMPANY, self.event)

		self.assertEqual(frappe.flags.commera_claim_calls, [])
		self.assertEqual(self.delivery(event_key), {"status": "Failed", "attempts": 0})

	def test_a_handler_that_commits_on_its_own_still_ends_done_once(self):
		event_key = self.fire_committed_event(commit_inside_handler)

		run_app_deliveries("commera", "Company", COMPANY, self.event)
		run_app_deliveries("commera", "Company", COMPANY, self.event)

		self.assertEqual(frappe.flags.commera_claim_calls, [event_key])
		self.assertEqual(self.delivery(event_key), {"status": "Done", "attempts": 1})

	def add_running_delivery(self, claimed_minutes_ago: int) -> str:
		key = frappe.generate_hash(length=10)
		with patch.object(frappe, "get_hooks", return_value={}):
			fire_event(self.event, "Company", COMPANY, key=key)
		event_key = f"{self.event}-{key}"
		frappe.get_doc("Commera Event", event_key).append(
			"deliveries",
			{
				"app": "commera",
				"handler": "commera.handler",
				"status": "Running",
				"claimed_at": add_to_date(now_datetime(), minutes=-claimed_minutes_ago),
			},
		).db_insert()
		return event_key

	def test_the_sweep_requeues_a_claim_its_worker_abandoned_as_a_failed_attempt(self):
		abandoned = self.add_running_delivery(claimed_minutes_ago=STALE_CLAIM_MINUTES + 1)
		running = self.add_running_delivery(claimed_minutes_ago=5)

		run_due_deliveries()

		self.assertEqual(self.delivery(abandoned), {"status": "Queued", "attempts": 1})
		self.assertEqual(self.delivery(running), {"status": "Running", "attempts": 0})

	def test_the_sweep_queues_each_due_lane_once_and_skips_one_waiting_on_a_retry(self):
		sales_order = make_test_sales_order(submit=False).name
		patch_app_hooks(
			self,
			{
				"commera_events": {
					"order_placed": [RECORD_APP_EVENT],
					"order_paid": [RECORD_APP_EVENT],
					self.event: [RECORD_APP_EVENT],
				}
			},
		)
		fire_event("order_placed", "Sales Order", sales_order)
		fire_event("order_paid", "Sales Order", sales_order)
		fire_event(self.event, "Company", COMPANY, key=frappe.generate_hash(length=10))
		self.enqueue.reset_mock()

		with patch("commera.app_events.enqueue_app_deliveries") as enqueue_lane:
			run_due_deliveries()
			frappe.db.set_value(
				"Commera Event Delivery",
				{"parent": f"{sales_order}-order_placed"},
				{"attempts": 1, "next_retry_at": add_to_date(now_datetime(), minutes=5)},
			)
			run_due_deliveries()

		lanes = [call.args for call in enqueue_lane.call_args_list]
		order_lane = ("commera", "Sales Order", sales_order, None)
		company_lane = ("commera", "Company", COMPANY, self.event)
		self.assertEqual(lanes.count(order_lane), 1, "one job for both order events, none once it waits")
		self.assertEqual(lanes.count(company_lane), 2)

	def test_a_new_event_is_queued_even_while_its_lane_job_is_running(self):
		for job_status, deduplicate in ((JobStatus.QUEUED, True), (JobStatus.STARTED, False)):
			self.enqueue.reset_mock()
			with patch("commera.app_events.get_job_status", return_value=job_status):
				enqueue_app_deliveries("commera", "Company", COMPANY, self.event)
			self.assertEqual(self.enqueue.call_args.kwargs["deduplicate"], deduplicate, job_status)


class TestProductUpdatedEvent(ProductOnboardingTestCase):
	make_named_attribute = test_admin_catalog.DeleteProductTestCase.make_named_attribute
	record_app_events = payment_hooks.TestPaymentHookIdempotency.record_app_events
	run_enqueued_jobs_now = payment_hooks.TestPaymentHookIdempotency.run_enqueued_jobs_now

	def setUp(self):
		super().setUp()
		patch_app_hooks(self, {"commera_events": {"product_updated": [RECORD_APP_EVENT]}})
		self.calls = self.record_app_events()
		self.product, self.option = self.add_listed_product()
		start_recording_product_changes()

	def add_listed_product(self):
		product = create_product(
			title=f"Events Product {frappe.generate_hash(length=6).upper()}",
			collection=self.item_group,
			option_attribute=self.make_named_attribute("Colour", ["Crimson"]),
			size_attribute="Size",
			option_sizes=[{"option": "Crimson", "sizes": ["S", "M"]}],
			price=500,
			sale_price=400,
		)["name"]
		option = frappe.get_all("Style Attribute Variant", {"item_style": product}, pluck="name")[0]
		frappe.get_doc(
			{
				"doctype": "Website Slideshow Item",
				"name": frappe.generate_hash(length=10),
				"parent": option,
				"parenttype": "Style Attribute Variant",
				"parentfield": "images",
				"image": f"/files/{frappe.generate_hash(length=8)}.png",
			}
		).db_insert()
		frappe.db.set_value("Style Attribute Variant", option, "is_published", 1)
		return product, option

	def get_product_sizes(self):
		return frappe.get_all("Item", {"variant_of": self.product}, pluck="name", order_by="name")

	def announced_changes(self):
		self.run_enqueued_jobs_now()
		frappe.db.after_commit.run()
		return [(event.reference_name, event.data) for event, user in self.calls]

	def assert_announced(self, *changed):
		self.assertEqual(
			self.announced_changes(), [(self.product, {"item_code": self.product, "changed": list(changed)})]
		)

	def test_a_size_item_save_is_announced_on_its_product(self):
		size_item = frappe.get_doc("Item", self.get_product_sizes()[0])
		size_item.description = frappe.generate_hash(length=10)
		size_item.save()

		self.assert_announced("details")

	def test_repricing_an_option_is_announced(self):
		set_variant_price(self.option, default_rate=600)

		self.assert_announced("price")

	def test_editing_one_size_price_is_announced(self):
		save_product_prices(self.option, [{"item_code": self.get_product_sizes()[0], "default_rate": 700}])

		self.assert_announced("price")

	def test_two_price_edits_in_one_transaction_are_one_price_event(self):
		set_variant_price(self.option, default_rate=600)
		save_product_prices(self.option, [{"item_code": self.get_product_sizes()[0], "default_rate": 700}])

		self.assert_announced("price")

	def test_unpublishing_the_last_option_in_bulk_is_announced_though_it_unlists_the_product(self):
		set_variants_published(0, [self.option])

		self.assert_announced("published")

	def test_unpublishing_one_option_is_announced(self):
		set_variant_published(self.option, 0)

		self.assert_announced("published")

	def test_removing_a_size_is_announced_as_an_options_change(self):
		save_product_options(self.product, remove=[{"option": "Crimson", "size": "M"}])

		self.assert_announced("options")

	def test_an_unlisted_products_edit_is_not_announced(self):
		set_variant_published(self.option, 0)
		start_recording_product_changes()

		set_variant_price(self.option, default_rate=600)

		self.assertEqual(self.announced_changes(), [])

	def test_a_rolled_back_change_never_stops_the_next_transactions_from_being_announced(self):
		set_variant_price(self.option, default_rate=600)
		frappe.db.rollback()

		super().setUp()
		self.product, self.option = self.add_listed_product()
		set_variant_price(self.option, default_rate=600)

		self.assert_announced("price")
