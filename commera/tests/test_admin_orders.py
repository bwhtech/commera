# Copyright (c) 2026, company@bwhstudios.com and Contributors
# Tests for the fulfilment ladder behind every order badge (api/admin/orders.py).

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils.data import add_days, cstr, get_year_ending, get_year_start, getdate

from commera.api.admin.orders import (
	MAX_PAGE_LENGTH,
	OPEN_STATUSES,
	OVERVIEW_WINDOW_DAYS,
	SETTLED_STAGES,
	STAGE_LABELS,
	STEP_SEQUENCE,
	can_fulfil_order,
	describe_progress,
	describe_state,
	fulfil_order,
	get_address_lines,
	get_order,
	get_orders,
	get_overview,
	read_order_lifecycles,
)
from commera.api.analytics_dashboard import get_period_kpis
from commera.utils import COD_CHARGE_DESCRIPTION

COMPANY = "Lifestyle Demo"
ITEM_GROUP = "Interior Accessories"
CURRENCY = "INR"
ITEM_RATE = 150.0


def to_fulfil_names() -> list:
	return [row["name"] for row in get_orders(status="open", page_length=MAX_PAGE_LENGTH)["orders"]]


def get_company_account(exclude=None):
	"""Any real expense account of the test company - these tests care where a charge points, not which."""
	return frappe.db.get_value(
		"Account",
		{"company": COMPANY, "is_group": 0, "root_type": "Expense", "name": ["!=", exclude or ""]},
		"name",
	)


def make_shipping_rule(shipping_amount):
	rule = frappe.new_doc("Shipping Rule")
	rule.label = f"ZZ Flat Shipping {frappe.generate_hash(length=6)}"
	rule.shipping_rule_type = "Selling"
	rule.calculate_based_on = "Net Total"
	rule.company = COMPANY
	rule.account = get_company_account()
	rule.cost_center = frappe.db.get_value("Cost Center", {"company": COMPANY, "is_group": 0}, "name")
	rule.append("conditions", {"from_value": 0, "to_value": 1000000, "shipping_amount": shipping_amount})
	rule.insert()
	return rule


def make_test_sales_order(order_type="Sales", submit=True, shipping_rule=None, cod_charge=0):
	"""A submitted order for a non-stock item: enough to fulfil and return, no stock ledger in the way."""
	ensure_fiscal_year()
	item_code = f"ZZ-LADDER-{frappe.generate_hash(length=8)}"
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": "ZZ Fulfilment Ladder Item",
			"item_group": ITEM_GROUP,
			"stock_uom": "Nos",
			"is_stock_item": 0,
		}
	).insert(ignore_permissions=True)

	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"ZZ Ladder Customer {frappe.generate_hash(length=8)}",
			"customer_type": "Individual",
		}
	).insert(ignore_permissions=True)

	sales_order = frappe.new_doc("Sales Order")
	sales_order.update(
		{
			"customer": customer.name,
			"company": COMPANY,
			"currency": CURRENCY,
			"conversion_rate": 1,
			"transaction_date": getdate(),
			"delivery_date": getdate(),
			"order_type": order_type,
			"items": [{"item_code": item_code, "qty": 2, "rate": ITEM_RATE}],
		}
	)
	if shipping_rule:
		sales_order.shipping_rule = shipping_rule

	sales_order.flags.ignore_permissions = True
	sales_order.insert()
	if shipping_rule:
		# ERPNext appends the rule's charge row only when run against a costed document.
		sales_order.run_method("apply_shipping_rule")
		sales_order.save()
	if cod_charge:
		# ERPNext re-applies the shipping rule on every save and overwrites the last row matching its
		# account and cost centre, so a COD row sharing them comes back holding the shipping amount.
		account = get_company_account(
			exclude=frappe.db.get_value("Shipping Rule", shipping_rule, "account") if shipping_rule else None
		)
		sales_order.append(
			"taxes",
			{
				"description": COD_CHARGE_DESCRIPTION,
				"charge_type": "Actual",
				"account_head": account,
				"tax_amount": cod_charge,
				"included_in_print_rate": 0,
			},
		)
		sales_order.save()
	if submit:
		sales_order.submit()
	return sales_order


def ensure_fiscal_year(on_date=None):
	"""This site was never given one, and every submitted selling document needs one."""
	on_date = getdate(on_date or getdate())
	year_start = get_year_start(on_date)
	if frappe.db.exists("Fiscal Year", {"year_start_date": year_start, "disabled": 0}):
		return
	frappe.get_doc(
		{
			"doctype": "Fiscal Year",
			"year": str(year_start.year),
			"year_start_date": year_start,
			"year_end_date": get_year_ending(on_date),
		}
	).insert(ignore_permissions=True, ignore_if_duplicate=True)


def return_against_order(sales_order):
	"""Ship the order and take it straight back - resets per_delivered while ERPNext's status stays open."""
	# ERPNext moved its transaction mappers to a sibling `mapper` module; both layouts are in the wild.
	try:
		from erpnext.stock.doctype.delivery_note.mapper import make_sales_return
	except ImportError:
		from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_return

	delivery_note = fulfil_order(sales_order.name)["delivery_note"]
	sales_return = make_sales_return(delivery_note)
	sales_return.flags.ignore_permissions = True
	sales_return.insert()
	sales_return.submit()
	return sales_return


def make_order(**values):
	order = frappe._dict(
		{
			"docstatus": 1,
			"status": "To Deliver",
			"per_delivered": 0,
			"lines": [frappe._dict({"qty": 2, "delivered_qty": 0, "delivered_by_supplier": 0})],
		}
	)
	order.update(values)
	return order


class TestFulfilmentLadder(UnitTestCase):
	def test_a_plain_confirmed_order_is_waiting_on_the_owner(self):
		self.assertEqual(describe_state(make_order())["key"], "to_fulfil")

	def test_the_label_is_the_owner_facing_wording_for_the_key(self):
		state = describe_state(make_order())
		self.assertEqual(state["label"], STAGE_LABELS["to_fulfil"])

	def test_an_unsubmitted_order_reads_as_awaiting_confirmation_not_as_draft(self):
		state = describe_state(make_order(docstatus=0, status="Draft"))
		self.assertEqual(state["key"], "confirmation_pending")
		self.assertEqual(state["label"], STAGE_LABELS["confirmation_pending"])

	def test_a_cancelled_order_outranks_every_other_rung(self):
		lifecycle = frappe._dict(has_return=True, stage_from_shipment="delivered")
		state = describe_state(make_order(docstatus=2, per_delivered=100), lifecycle)
		self.assertEqual(state["key"], "cancelled")

	def test_a_draft_delivery_note_reads_as_drafted_not_as_waiting(self):
		lifecycle = frappe._dict(has_draft_delivery_note=True)
		self.assertEqual(describe_state(make_order(), lifecycle)["key"], "delivery_note_drafted")

	def test_a_packing_slip_advances_a_drafted_delivery_note_to_packed(self):
		lifecycle = frappe._dict(has_draft_delivery_note=True, has_packing_slip=True)
		self.assertEqual(describe_state(make_order(), lifecycle)["key"], "packed")

	def test_packing_never_outranks_fulfilment(self):
		"""ERPNext only allows a Packing Slip against a draft Delivery Note, so the slip that is
		still linked once that note is submitted must not drag a shipped order back to "Packed"."""
		lifecycle = frappe._dict(has_packing_slip=True)
		order = make_order(status="Completed", per_delivered=100)
		self.assertEqual(describe_state(order, lifecycle)["key"], "fulfilled")

	def test_a_part_shipped_order_is_partly_fulfilled(self):
		self.assertEqual(describe_state(make_order(per_delivered=40))["key"], "partly_fulfilled")

	def test_the_carrier_status_outranks_the_paperwork(self):
		lifecycle = frappe._dict(stage_from_shipment="delivered", has_packing_slip=True)
		order = make_order(status="Completed", per_delivered=100)
		self.assertEqual(describe_state(order, lifecycle)["key"], "delivered")

	def test_a_return_outranks_the_fulfilment_it_reverses(self):
		lifecycle = frappe._dict(has_return=True)
		order = make_order(status="Completed", per_delivered=100)
		self.assertEqual(describe_state(order, lifecycle)["key"], "returned")

	def test_a_status_the_ladder_has_no_rung_for_keeps_erpnexts_own_word(self):
		state = describe_state(make_order(status="On Hold"))
		self.assertEqual(state, {"key": "On Hold", "label": "On Hold"})


class TestFulfilmentSteps(UnitTestCase):
	"""The stepper draws a sequence; the ladder is a priority ordering. These pin the translation."""

	def keys(self, order, lifecycle=None):
		return [step["key"] for step in describe_progress(order, lifecycle)]

	def states(self, order, lifecycle=None):
		return {step["key"]: step["state"] for step in describe_progress(order, lifecycle)}

	def test_a_new_order_stands_on_the_first_node_with_the_rest_ahead_of_it(self):
		steps = describe_progress(make_order(docstatus=0, status="Draft"))
		self.assertEqual([step["key"] for step in steps], list(STEP_SEQUENCE))
		self.assertEqual(steps[0]["state"], "current")
		self.assertTrue(all(step["state"] == "upcoming" for step in steps[1:]))

	def test_an_unsubmitted_order_stands_on_the_confirmation_node(self):
		states = self.states(make_order(docstatus=0, status="Draft"))
		self.assertEqual(states["confirmation_pending"], "current")
		self.assertEqual(states["to_fulfil"], "upcoming")

	def test_the_node_the_owner_is_on_is_the_ladder_s_own_answer(self):
		lifecycle = frappe._dict(has_draft_delivery_note=True, has_packing_slip=True)
		order = make_order()
		self.assertEqual(self.states(order, lifecycle)["packed"], "current")
		self.assertEqual(describe_state(order, lifecycle)["key"], "packed")

	def test_everything_before_the_current_node_reads_as_done(self):
		lifecycle = frappe._dict(stage_from_shipment="shipped")
		states = self.states(make_order(), lifecycle)
		self.assertEqual(states["to_fulfil"], "done")
		self.assertEqual(states["delivery_note_drafted"], "done")
		self.assertEqual(states["packed"], "done")
		self.assertEqual(states["shipped"], "current")
		self.assertEqual(states["delivered"], "upcoming")

	def test_a_quantity_rung_annotates_the_dispatch_node_rather_than_adding_one(self):
		""" "Partly fulfilled" says how much went out, not where the order is, so it must not become
		a circle of its own - it would be a step no order ever has to pass through."""
		steps = describe_progress(make_order(per_delivered=40))
		self.assertEqual([step["key"] for step in steps], list(STEP_SEQUENCE))
		shipped = next(step for step in steps if step["key"] == "shipped")
		self.assertEqual(shipped["state"], "current")
		self.assertEqual(shipped["note"], STAGE_LABELS["partly_fulfilled"])

	def test_a_fully_fulfilled_order_has_not_yet_been_delivered(self):
		order = make_order(status="Completed", per_delivered=100)
		states = self.states(order)
		self.assertEqual(states["shipped"], "current")
		self.assertEqual(states["delivered"], "upcoming")

	def test_a_cancelled_order_ends_the_path_instead_of_leaving_it_half_walked(self):
		steps = describe_progress(make_order(docstatus=2))
		self.assertEqual([step["key"] for step in steps], ["confirmation_pending", "to_fulfil", "cancelled"])
		self.assertEqual(steps[-1]["state"], "current")
		self.assertNotIn("upcoming", [step["state"] for step in steps])

	def test_a_cancelled_order_keeps_the_nodes_it_did_reach(self):
		lifecycle = frappe._dict(has_packing_slip=True, has_draft_delivery_note=True)
		self.assertEqual(
			self.keys(make_order(docstatus=2), lifecycle),
			["confirmation_pending", "to_fulfil", "delivery_note_drafted", "packed", "cancelled"],
		)

	def test_a_returned_order_walked_as_far_as_dispatch_and_stops_there(self):
		"""A return is what reset per_delivered, so the goods provably went out - but a parcel that
		came back was never delivered, and the path must not offer Delivered as still to come."""
		lifecycle = frappe._dict(has_return=True, delivery_notes=["MAT-DN-0001"])
		steps = describe_progress(make_order(), lifecycle)
		self.assertEqual(
			[step["key"] for step in steps],
			[
				"confirmation_pending",
				"to_fulfil",
				"delivery_note_drafted",
				"packed",
				"shipped",
				"returned",
			],
		)
		self.assertEqual(steps[-1]["state"], "current")
		self.assertNotIn("delivered", [step["key"] for step in steps])

	def test_a_delivered_parcel_that_came_back_keeps_its_delivery(self):
		lifecycle = frappe._dict(has_return=True, stage_from_shipment="delivered")
		# The carrier delivered it, so `pick_stage` reads delivered and the path has not ended.
		self.assertEqual(self.keys(make_order(), lifecycle)[-1], "delivered")

	def test_an_rto_parcel_never_arrived(self):
		lifecycle = frappe._dict(stage_from_shipment="returned")
		self.assertEqual(self.keys(make_order(), lifecycle)[-1], "returned")

	def test_a_status_the_sequence_has_no_node_for_still_gets_said(self):
		"""On Hold and Closed are not rungs, so they have no circle to stand on. The order stands on
		what the paperwork proves instead, and ERPNext's own word rides along as the caption."""
		steps = describe_progress(make_order(status="On Hold"))
		current = next(step for step in steps if step["state"] == "current")
		self.assertEqual(current["key"], "to_fulfil")
		self.assertEqual(current["note"], "On Hold")

	def test_an_off_ladder_order_stands_as_far_along_as_its_documents_reach(self):
		lifecycle = frappe._dict(delivery_notes=["MAT-DN-0001"])
		states = self.states(make_order(status="On Hold"), lifecycle)
		self.assertEqual(states["delivery_note_drafted"], "current")
		self.assertEqual(states["to_fulfil"], "done")

	def test_every_node_is_named_for_a_person_not_by_its_key(self):
		for step in describe_progress(make_order(docstatus=2)):
			with self.subTest(step=step["key"]):
				self.assertNotEqual(step["label"], step["key"])
				self.assertTrue(step["label"])


class TestAddressLines(UnitTestCase):
	"""ERPNext hands over address_display as HTML, so <br> tags used to appear literally on the screen."""

	def test_break_tags_become_newlines(self):
		self.assertEqual(
			get_address_lines("12 King Fahd Road<br>Near Mall<br>Riyadh"),
			"12 King Fahd Road\nNear Mall\nRiyadh",
		)

	def test_the_self_closing_and_uppercase_spellings_break_too(self):
		self.assertEqual(get_address_lines("A<br/>B<BR />C"), "A\nB\nC")

	def test_surrounding_markup_is_stripped_rather_than_shown(self):
		self.assertEqual(get_address_lines("<div>Riyadh</div><br><span>SA</span>"), "Riyadh\nSA")

	def test_blank_segments_do_not_become_empty_lines(self):
		self.assertEqual(get_address_lines("Riyadh<br><br>   <br>SA"), "Riyadh\nSA")

	def test_an_address_with_nothing_in_it_reads_as_absent(self):
		for empty in (None, "", "<br><br>"):
			self.assertIsNone(get_address_lines(empty))


class TestOrderLifecycleReader(IntegrationTestCase):
	def test_no_orders_costs_no_queries(self):
		self.assertEqual(read_order_lifecycles([]), {})

	def test_an_autoincrement_named_order_is_keyed_as_a_string(self):
		"""A Sales Order named by autoincrement arrives as an int, and the caller looks it up
		with cstr(name) - the two have to meet on the same key or every badge falls back."""
		self.assertEqual(list(read_order_lifecycles([41])), ["41"])

	def test_an_order_with_no_paperwork_reads_back_empty(self):
		order = frappe.get_all("Sales Order", filters={"docstatus": 1}, limit=1, pluck="name")
		if not order:
			self.skipTest("no submitted Sales Order on this site")

		lifecycle = read_order_lifecycles(order)[order[0]]
		self.assertIsInstance(lifecycle.delivery_notes, list)

	def test_a_page_of_orders_costs_the_same_reads_as_a_single_one(self):
		"""The whole point of the reader: the badge column must not scale with the page size."""
		# Every order here must carry a delivery note: one with no paperwork skips the note and
		# packing-slip reads entirely, so mixing shapes measures the sample, not whether it scales.
		orders = sorted(
			{
				cstr(row.against_sales_order)
				for row in frappe.get_all(
					"Delivery Note Item",
					filters={"against_sales_order": ["!=", ""], "docstatus": ["<", 2]},
					fields=["against_sales_order"],
					limit=40,
				)
			}
		)[:5]
		if len(orders) < 2:
			self.skipTest("needs at least two Sales Orders with a delivery note on this site")

		# Warm the doctype meta first: the first read of a doctype in a process pays for its schema.
		read_order_lifecycles(orders)

		one_order_queries = count_queries(orders[:1])
		self.assertEqual(count_queries(orders), one_order_queries)


def count_queries(order_names: list) -> int:
	calls = []
	original_sql = frappe.db.sql

	def counting_sql(query, *args, **kwargs):
		calls.append(query)
		return original_sql(query, *args, **kwargs)

	frappe.db.sql = counting_sql
	try:
		read_order_lifecycles(order_names)
	finally:
		frappe.db.sql = original_sql
	return len(calls)


class TestFulfilButton(UnitTestCase):
	"""per_delivered alone used to decide this, and a return resets per_delivered."""

	def test_no_settled_rung_offers_the_button(self):
		for key in SETTLED_STAGES:
			with self.subTest(stage=key):
				self.assertFalse(can_fulfil_order(make_order(), {"key": key}))

	def test_an_order_still_waiting_on_the_owner_offers_it(self):
		self.assertTrue(can_fulfil_order(make_order(), {"key": "to_fulfil"}))

	def test_a_part_shipped_order_still_has_something_left_to_ship(self):
		self.assertTrue(can_fulfil_order(make_order(per_delivered=40), {"key": "partly_fulfilled"}))

	def test_a_fully_delivered_order_has_nothing_left_to_ship(self):
		self.assertFalse(can_fulfil_order(make_order(per_delivered=100), {"key": "fulfilled"}))

	def test_a_draft_order_cannot_be_fulfilled(self):
		self.assertFalse(can_fulfil_order(make_order(docstatus=0), {"key": "to_fulfil"}))


class TestToFulfilAgreement(IntegrationTestCase):
	"""The badge, the tab, the Home figure and the fulfil button all have to tell the same story."""

	def setUp(self):
		self.sales_order = make_test_sales_order()

	def test_an_open_order_is_in_the_to_fulfil_tab(self):
		self.assertIn(self.sales_order.name, to_fulfil_names())

	def test_a_returned_order_leaves_the_to_fulfil_tab(self):
		return_against_order(self.sales_order)

		state = get_order(self.sales_order.name)["state"]
		self.assertEqual(state["key"], "returned")
		self.assertNotIn(self.sales_order.name, to_fulfil_names())

	def test_a_returned_order_still_reads_as_open_to_erpnext(self):
		"""Without this the fix would be untested: the exclusion only matters while the raw status
		disagrees with the ladder."""
		return_against_order(self.sales_order)

		status = frappe.db.get_value("Sales Order", self.sales_order.name, "status")
		self.assertIn(status, OPEN_STATUSES)

	def test_a_returned_order_offers_no_fulfil_button(self):
		return_against_order(self.sales_order)

		self.assertFalse(get_order(self.sales_order.name)["can_fulfil"])

	def test_a_returned_order_refuses_to_be_fulfilled(self):
		"""The button is gone, but a screen left open on a stale list can still call this."""
		return_against_order(self.sales_order)

		with self.assertRaises(frappe.ValidationError):
			fulfil_order(self.sales_order.name)

	def test_the_home_figure_counts_exactly_the_to_fulfil_list(self):
		return_against_order(self.sales_order)

		to_fulfil = next(stat for stat in get_overview()["stats"] if stat["key"] == "to_fulfil")
		self.assertEqual(to_fulfil["value"], get_orders(status="open")["total"])

	def test_the_stepper_dates_the_nodes_it_can_and_leaves_the_rest_blank(self):
		"""Timestamps ride along on reads the lifecycle already does, so they have to survive the
		trip: the order date and the dispatch date come from real documents here."""
		fulfil_order(self.sales_order.name)

		steps = {step["key"]: step for step in get_order(self.sales_order.name)["progress"]}
		self.assertEqual(steps["to_fulfil"]["at"], self.sales_order.transaction_date)
		self.assertTrue(steps["delivery_note_drafted"]["at"])
		self.assertTrue(steps["shipped"]["at"])
		# Nothing was packed and no carrier moved it, so those nodes have no document to date them.
		self.assertIsNone(steps["packed"]["at"])

	def test_a_returned_order_reads_the_same_on_the_stepper_as_on_its_badge(self):
		return_against_order(self.sales_order)

		detail = get_order(self.sales_order.name)
		self.assertEqual(detail["state"]["key"], "returned")
		self.assertEqual(detail["progress"][-1]["key"], "returned")
		self.assertEqual(detail["progress"][-1]["state"], "current")
		self.assertTrue(detail["progress"][-1]["at"])

	def test_the_tab_never_shows_an_order_wearing_a_settled_badge(self):
		"""The bug in one line: every row of the worklist has to be an order the owner can still act on."""
		return_against_order(self.sales_order)

		page = get_orders(status="open", page_length=MAX_PAGE_LENGTH)
		self.assertEqual(len(page["orders"]), min(page["total"], MAX_PAGE_LENGTH))
		for row in page["orders"]:
			with self.subTest(order=row["name"]):
				self.assertNotIn(row["state"]["key"], SETTLED_STAGES)


class TestDropShipFulfilment(IntegrationTestCase):
	"""A drop-ship line is the supplier's to ship, so the store's fulfil flow must leave it alone."""

	def test_a_drop_ship_only_order_offers_and_allows_no_fulfilment(self):
		sales_order = make_drop_ship_order()

		self.assertFalse(get_order(sales_order.name)["can_fulfil"])
		with self.assertRaises(frappe.ValidationError):
			fulfil_order(sales_order.name)
		self.assertFalse(frappe.db.exists("Delivery Note Item", {"against_sales_order": sales_order.name}))

	def test_a_mixed_order_fulfils_only_the_store_line(self):
		sales_order = make_drop_ship_order(with_store_line=True)
		store_line = next(line for line in sales_order.items if not line.delivered_by_supplier)
		self.assertTrue(get_order(sales_order.name)["can_fulfil"])

		delivery_note = frappe.get_doc("Delivery Note", fulfil_order(sales_order.name)["delivery_note"])

		self.assertEqual([line.so_detail for line in delivery_note.items], [store_line.name])
		self.assertFalse(get_order(sales_order.name)["can_fulfil"])


def make_drop_ship_order(with_store_line: bool = False):
	sales_order = make_test_sales_order(submit=False)
	if with_store_line:
		sales_order.append(
			"items", {"item_code": sales_order.items[0].item_code, "qty": 1, "rate": ITEM_RATE}
		)
	sales_order.items[0].update({"delivered_by_supplier": 1, "supplier": get_drop_ship_supplier()})
	sales_order.save()
	sales_order.submit()
	return sales_order


def get_drop_ship_supplier() -> str:
	supplier_name = "ZZ Drop Ship Supplier"
	if not frappe.db.exists("Supplier", supplier_name):
		frappe.get_doc({"doctype": "Supplier", "supplier_name": supplier_name}).insert(
			ignore_permissions=True
		)
	return supplier_name


class TestRevenueDefinition(IntegrationTestCase):
	"""Home's Revenue tile and Analytics' Total sales read one definition: a storefront order not
	cancelled. Drafts count because cash on delivery places its order as a draft."""

	def get_home_stat(self, key):
		return next(stat for stat in get_overview()["stats"] if stat["key"] == key)["value"]

	def get_analytics_kpis(self):
		today = getdate()
		return get_period_kpis(add_days(today, -(OVERVIEW_WINDOW_DAYS - 1)), today)

	def test_a_draft_storefront_order_is_revenue_on_both_screens(self):
		before_home = self.get_home_stat("revenue")
		before_analytics = self.get_analytics_kpis()["total_sales"]

		sales_order = make_test_sales_order(order_type="Shopping Cart", submit=False)

		self.assertEqual(sales_order.docstatus, 0)
		self.assertAlmostEqual(
			self.get_home_stat("revenue"), before_home + sales_order.base_grand_total, places=2
		)
		self.assertAlmostEqual(
			self.get_analytics_kpis()["total_sales"],
			before_analytics + sales_order.base_grand_total,
			places=2,
		)

	def test_an_order_keyed_in_by_hand_is_not_storefront_revenue(self):
		before_home = self.get_home_stat("revenue")
		before_analytics = self.get_analytics_kpis()["total_sales"]

		make_test_sales_order(order_type="Sales")

		self.assertAlmostEqual(self.get_home_stat("revenue"), before_home, places=2)
		self.assertAlmostEqual(self.get_analytics_kpis()["total_sales"], before_analytics, places=2)

	def test_a_cancelled_storefront_order_is_revenue_on_neither(self):
		sales_order = make_test_sales_order(order_type="Shopping Cart")
		before_home = self.get_home_stat("revenue")

		sales_order.cancel()

		self.assertAlmostEqual(
			self.get_home_stat("revenue"), before_home - sales_order.base_grand_total, places=2
		)

	def test_the_two_screens_report_the_same_window(self):
		"""The defect in one line: Home and Analytics sit two clicks apart under the same label and
		used to disagree about the same thirty days."""
		make_test_sales_order(order_type="Shopping Cart", submit=False)
		make_test_sales_order(order_type="Shopping Cart")
		make_test_sales_order(order_type="Sales")

		analytics = self.get_analytics_kpis()
		self.assertAlmostEqual(self.get_home_stat("revenue"), analytics["total_sales"], places=2)
		self.assertEqual(self.get_home_stat("orders"), analytics["orders"])


SHIPPING_CHARGE = 40.0
COD_CHARGE = 15.0
SALES_TAX = 7.5


class TestOrderCharges(IntegrationTestCase):
	"""The order screen has to be able to name every riyal between the item lines and the total."""

	def setUp(self):
		self.shipping_rule = make_shipping_rule(SHIPPING_CHARGE)
		self.sales_order = make_test_sales_order(
			order_type="Shopping Cart",
			submit=False,
			shipping_rule=self.shipping_rule.name,
			cod_charge=COD_CHARGE,
		)

	def add_sales_tax(self, amount):
		self.sales_order.append(
			"taxes",
			{
				"description": "ZZ Sales Tax",
				"charge_type": "Actual",
				"account_head": get_company_account(exclude=self.shipping_rule.account),
				"tax_amount": amount,
				"included_in_print_rate": 0,
			},
		)
		self.sales_order.save()

	def test_shipping_and_cash_on_delivery_are_named_apart_from_tax(self):
		order = get_order(self.sales_order.name)

		self.assertEqual(order["shipping"], SHIPPING_CHARGE)
		self.assertEqual(order["cod_charge"], COD_CHARGE)
		self.assertEqual(order["tax"], 0)

	def test_cash_on_delivery_on_the_shipping_account_is_still_not_shipping(self):
		"""The live store points both charge rows at one account and one cost centre, so the pair
		cannot be what tells them apart - the row's own description has to win."""
		cod_row = frappe.db.get_value(
			"Sales Taxes and Charges",
			{"parent": self.sales_order.name, "description": COD_CHARGE_DESCRIPTION},
			"name",
		)
		frappe.db.set_value(
			"Sales Taxes and Charges",
			cod_row,
			{"account_head": self.shipping_rule.account, "cost_center": self.shipping_rule.cost_center},
		)

		order = get_order(self.sales_order.name)

		self.assertEqual(order["cod_charge"], COD_CHARGE)
		self.assertEqual(order["shipping"], SHIPPING_CHARGE)

	def test_the_breakdown_reconciles_with_the_grand_total(self):
		self.add_sales_tax(SALES_TAX)

		order = get_order(self.sales_order.name)

		self.assertEqual(order["tax"], SALES_TAX)
		self.assertAlmostEqual(
			order["net_total"] + order["shipping"] + order["cod_charge"] + order["tax"],
			order["grand_total"],
			places=2,
		)

	def test_the_named_lines_add_up_to_the_documents_own_charge_total(self):
		self.add_sales_tax(SALES_TAX)

		order = get_order(self.sales_order.name)

		self.assertAlmostEqual(
			order["shipping"] + order["cod_charge"] + order["tax"],
			order["total_taxes_and_charges"],
			places=2,
		)

	def test_an_order_with_no_charges_at_all_reads_as_zeroes(self):
		order = get_order(make_test_sales_order(order_type="Shopping Cart", submit=False).name)

		self.assertEqual(order["shipping"], 0)
		self.assertEqual(order["cod_charge"], 0)
		self.assertEqual(order["tax"], 0)
		self.assertEqual(order["net_total"], order["grand_total"])

	def test_the_screen_names_the_delivery_option_the_shopper_chose(self):
		"""A shipping amount alone cannot tell the owner which service to book."""
		self.sales_order.db_set("custom_delivery_option", "ZZ Express Delivery")

		self.assertEqual(get_order(self.sales_order.name)["delivery_option"], "ZZ Express Delivery")

	def test_an_order_that_took_the_flat_shipping_rule_names_no_option(self):
		self.assertFalse(get_order(self.sales_order.name)["delivery_option"])


def draft_delivery_note(sales_order):
	"""A Delivery Note left unsubmitted - what a merchant prints a packing slip from before the
	parcel is actually gone."""
	try:
		from erpnext.selling.doctype.sales_order.mapper import make_delivery_note
	except ImportError:
		from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

	delivery_note = make_delivery_note(sales_order.name)
	delivery_note.flags.ignore_permissions = True
	delivery_note.insert()
	return delivery_note


def invoice_against_order(sales_order):
	try:
		from erpnext.selling.doctype.sales_order.mapper import make_sales_invoice
	except ImportError:
		from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

	invoice = make_sales_invoice(sales_order.name)
	invoice.flags.ignore_permissions = True
	invoice.insert()
	invoice.submit()
	return invoice


def credit_note_against_invoice(invoice):
	"""ERPNext's return mapper copies `sales_order` onto the credit note's lines, so the credit note
	joins an order exactly the way its invoice does."""
	try:
		from erpnext.accounts.doctype.sales_invoice.mapper import make_sales_return
	except ImportError:
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

	credit_note = make_sales_return(invoice.name)
	credit_note.flags.ignore_permissions = True
	credit_note.insert()
	credit_note.submit()
	return credit_note


class TestPrintableDocuments(IntegrationTestCase):
	"""What the order screen hands a merchant to print. Every one of these is a document that opens
	under a button, so the wrong one in the list is a wrong sheet of paper."""

	def setUp(self):
		self.sales_order = make_test_sales_order()

	def test_the_submitted_and_the_printable_note_lists_stay_apart(self):
		"""They must not collapse back into one: the ladder is derived from submitted notes only,
		while the printable list is deliberately wider so a draft can be printed."""
		note = draft_delivery_note(self.sales_order)

		lifecycle = read_order_lifecycles([self.sales_order.name])[self.sales_order.name]

		self.assertEqual(lifecycle.delivery_notes, [])
		self.assertEqual(lifecycle.printable_delivery_notes, [note.name])

	def test_get_order_offers_the_draft_note_to_print(self):
		note = draft_delivery_note(self.sales_order)

		self.assertEqual(get_order(self.sales_order.name)["deliveries"], [note.name])

	def test_a_return_note_is_never_offered_for_printing(self):
		"""A sales return is paperwork for stock coming back; a bulk packing slip run that included
		it would put a refunded parcel back on the dispatch bench."""
		sales_return = return_against_order(self.sales_order)

		lifecycle = read_order_lifecycles([self.sales_order.name])[self.sales_order.name]

		self.assertIn(sales_return.name, lifecycle.delivery_notes)
		self.assertNotIn(sales_return.name, lifecycle.printable_delivery_notes)
		self.assertNotIn(sales_return.name, get_order(self.sales_order.name)["deliveries"])

	def test_a_credit_note_is_not_offered_as_an_invoice(self):
		invoice = invoice_against_order(self.sales_order)
		credit_note = credit_note_against_invoice(invoice)

		invoices = get_order(self.sales_order.name)["invoices"]

		self.assertEqual(invoices, [invoice.name])
		self.assertNotIn(credit_note.name, invoices)
