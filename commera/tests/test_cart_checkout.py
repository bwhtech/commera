# Copyright (c) 2026, company@bwhstudios.com and Contributors
# The storefront checkout writes as the shopper, who has no Account read; see payments.save_cart_quotation.

from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase

from commera.api.cart import get_detail_for_cart_items, get_stock_shortfalls, validate_stock_available
from commera.api.checkout import apply_shipping_rule
from commera.api.payments import (
	COD_PAYMENT_MODE,
	confirm_payment,
	generate_quotation_for_cart,
	initiate_checkout_with_mode,
	save_cart_quotation,
	update_delivery_charges,
	update_quotation_address,
)
from commera.api.shipping import (
	get_cart_fingerprint,
	get_checkout_summary,
	get_order_charge_lines,
	set_delivery_option,
)
from commera.core import _get_cart_quotation
from commera.tests.test_admin_orders import ensure_fiscal_year
from commera.utils import get_pickup_addresses
from commera.www.cart.checkout import get_context as get_checkout_context
from commera.www.cart.checkout import get_store_pickup_addresses

COUNTRY = "Saudi Arabia"
PIN_GEOJSON = frappe.as_json(
	{
		"type": "FeatureCollection",
		"features": [
			{
				"type": "Feature",
				"properties": {},
				"geometry": {"type": "Point", "coordinates": [46.6753, 24.7136]},
			}
		],
	}
)
IN_STOCK_QTY = 4.0
DEFAULT_RATE = 120.0
SALE_RATE = 90.0
TAX_DESCRIPTION = "ZZ Output Tax"
TAX_RATE = 18.0


class TestCartCheckout(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		commera_settings = frappe.get_cached_doc("Commera Settings")
		cls.default_price_list = commera_settings.get_default_price_list()
		cls.sale_price_list = commera_settings.get_sale_price_list()
		cls.warehouse = commera_settings.ecommerce_warehouse

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		self.shopper = self.create_shopper()
		self.discounted_item = self.create_item(sale_rate=SALE_RATE)
		self.full_price_item = self.create_item(sale_rate=None)

	# -- fixtures ---------------------------------------------------------------------------------

	def create_shopper(self) -> str:
		"""A storefront signup: a Website User holding only the Customer role, so no Account read."""
		email = f"zz-shopper-{frappe.generate_hash(length=8)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "ZZ Shopper",
				"last_name": "Checkout",
				"send_welcome_email": 0,
				"user_type": "Website User",
			}
		)
		user.append("roles", {"role": "Customer"})
		user.insert(ignore_permissions=True)
		return email

	def create_item(self, sale_rate: float | None) -> str:
		item_code = f"ZZ-CART-{frappe.generate_hash(length=8)}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": "ZZ Cart Item",
				"item_group": frappe.get_all("Item Group", {"is_group": 0}, pluck="name", limit=1)[0],
				"stock_uom": "Nos",
				"is_stock_item": 1,
			}
		).insert(ignore_permissions=True)

		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": self.default_price_list,
				"price_list_rate": DEFAULT_RATE,
			}
		).insert(ignore_permissions=True)
		if sale_rate is not None:
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": item_code,
					"price_list": self.sale_price_list,
					"price_list_rate": sale_rate,
				}
			).insert(ignore_permissions=True)

		# Bin is how commera.utils.get_available_stocks reads sellable qty; erpnext creates it the same way.
		frappe.get_doc(
			{
				"doctype": "Bin",
				"item_code": item_code,
				"warehouse": self.warehouse,
				"actual_qty": IN_STOCK_QTY,
			}
		).insert(ignore_permissions=True)
		return item_code

	def cart_line(self, item_code: str, qty: float) -> dict:
		return {"item": {"display_name": "ZZ Cart Item"}, "variant": {"item_code": item_code}, "qty": qty}

	def address_payload(self) -> dict:
		return {
			"billing_address": {
				"full_address": "1 Billing Street",
				"city": "Riyadh",
				"country": COUNTRY,
				"phone_number": "+966500000001",
				"email": self.shopper,
				"first_name": "ZZ",
				"last_name": "Shopper",
			},
			"shipping_same_as_billing": True,
		}

	# -- the blocker: every cart write happens in the shopper's own session -------------------------

	def test_shopper_cannot_read_accounts(self):
		"""Guards the tests below: without this the elevated save would be proving nothing."""
		frappe.set_user(self.shopper)
		self.assertFalse(frappe.has_permission("Account", "read"))

	def test_shopper_generates_a_quotation_for_their_cart(self):
		frappe.set_user(self.shopper)

		quotation = generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 2)]})

		self.assertEqual(quotation.docstatus, 0)
		self.assertEqual([(row.item_code, row.qty) for row in quotation.items], [(self.discounted_item, 2)])
		self.assertEqual(quotation.contact_email, self.shopper)

	def test_shopper_saves_their_checkout_address(self):
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 1)]})

		update_quotation_address(self.address_payload())

		quotation = _get_cart_quotation()
		self.assertTrue(quotation.customer_address)
		self.assertEqual(quotation.shipping_address_name, quotation.customer_address)

	def test_shopper_applies_the_shipping_rule(self):
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 1)]})

		apply_shipping_rule()

		self.assertEqual(_get_cart_quotation().docstatus, 0)

	def test_the_shopper_session_survives_the_elevated_save(self):
		"""set_user() mutates local.session in place; a restore that round-trips it logs the shopper out."""
		frappe.set_user(self.shopper)
		session_before = frappe.local.session.copy()

		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 1)]})

		self.assertEqual(frappe.session.user, self.shopper)
		self.assertEqual(frappe.local.session, session_before)

	def test_the_delivery_option_save_runs_elevated(self):
		"""A cart save left in the shopper's session is refused by ERPNext's own Account and Item reads."""
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 1)]})

		users_at_save = []
		unpatched_save = Document.save

		def record_saving_user(document, *args, **kwargs):
			if document.doctype == "Quotation":
				users_at_save.append(frappe.session.user)
			return unpatched_save(document, *args, **kwargs)

		with patch.object(Document, "save", record_saving_user):
			set_delivery_option()

		self.assertTrue(users_at_save, "the cart was never saved")
		self.assertEqual(set(users_at_save), {"Administrator"})

	def stale_cart_snapshot(self):
		snapshot = frappe.get_doc("Quotation", _get_cart_quotation().name)
		save_cart_quotation(_get_cart_quotation())

		self.assertNotEqual(
			str(snapshot.modified),
			str(frappe.db.get_value("Quotation", snapshot.name, "modified")),
			"the snapshot is not stale, so the test would pass without the lock",
		)
		return snapshot

	def test_a_delivery_option_survives_a_cart_saved_after_its_snapshot(self):
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 1)]})
		snapshot = self.stale_cart_snapshot()
		modified_before = frappe.db.get_value("Quotation", snapshot.name, "modified")

		with patch("commera.api.shipping._get_cart_quotation", return_value=snapshot):
			set_delivery_option()

		self.assertGreater(frappe.db.get_value("Quotation", snapshot.name, "modified"), modified_before)

	def test_checkout_survives_a_cart_saved_after_its_snapshot(self):
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 1)]})
		update_quotation_address(self.address_payload())
		frappe.db.set_single_value("Commera Settings", "cod_enabled", 1)
		snapshot = self.stale_cart_snapshot()

		with patch("commera.api.payments._get_cart_quotation", return_value=snapshot):
			checkout = initiate_checkout_with_mode(COD_PAYMENT_MODE)

		self.assertIn(snapshot.name, checkout["order_url"])

	def test_the_rate_cache_key_holds_still_for_an_unchanged_cart(self):
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 1)]})
		quotation = _get_cart_quotation()
		fingerprint = get_cart_fingerprint(quotation)

		self.assertEqual(fingerprint, get_cart_fingerprint(quotation))

		quotation.items[0].qty = 2
		self.assertNotEqual(fingerprint, get_cart_fingerprint(quotation))

	# -- checkout summary -------------------------------------------------------------------------

	def get_output_tax_account(self, company: str) -> str:
		return frappe.db.get_value(
			"Account",
			{"company": company, "root_type": "Liability", "account_type": "", "is_group": 0},
			"name",
		)

	def add_tax_to_cart(self):
		"""An On Net Total tax row, as a GST template leaves on the cart once the address is known."""
		quotation = _get_cart_quotation()
		quotation.append(
			"taxes",
			{
				"charge_type": "On Net Total",
				"description": TAX_DESCRIPTION,
				"account_head": self.get_output_tax_account(quotation.company),
				"rate": TAX_RATE,
				"included_in_print_rate": 0,
			},
		)
		save_cart_quotation(quotation)

	def set_cod_fee(self, cod_charge: float):
		frappe.db.set_single_value(
			"Commera Settings",
			{
				"cod_enabled": 1,
				"cod_charge": cod_charge,
				"cod_charge_applicable_below": 100000,
				"charge_account_head": frappe.db.get_value(
					"Account",
					{"company": _get_cart_quotation().company, "root_type": "Income", "is_group": 0},
					"name",
				),
			},
		)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")
		self.addCleanup(frappe.clear_document_cache, "Commera Settings", "Commera Settings")

	def assert_summary_adds_up(self, summary: dict):
		self.assertAlmostEqual(
			summary["total"],
			summary["subtotal"]
			+ summary["shipping"]
			+ summary["cod_charge"]
			+ sum(tax["amount"] for tax in summary["taxes"])
			- summary["discount_amount"]
			+ summary["rounding_adjustment"],
			places=2,
		)

	def test_the_checkout_summary_names_the_tax_and_adds_up_to_its_total(self):
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 3)]})
		update_quotation_address(self.address_payload())
		self.add_tax_to_cart()

		summary = get_checkout_summary(_get_cart_quotation())

		self.assertEqual(summary["subtotal"], 270)
		self.assertEqual(summary["taxes"], [{"description": TAX_DESCRIPTION, "amount": 48.6}])
		self.assert_summary_adds_up(summary)

	def test_a_grand_total_coupon_shows_as_a_discount_the_lines_add_up_to(self):
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 3)]})
		update_quotation_address(self.address_payload())
		self.add_tax_to_cart()
		quotation = _get_cart_quotation()
		quotation.apply_discount_on = "Grand Total"
		quotation.discount_amount = 50
		save_cart_quotation(quotation)

		summary = get_checkout_summary(_get_cart_quotation())

		self.assertEqual(summary["subtotal"], 270)
		self.assertEqual(summary["discount_amount"], 50)
		self.assertEqual(summary["total"], round(270 + 48.6 + summary["shipping"] - 50))
		self.assert_summary_adds_up(summary)

	def test_the_cod_checkout_total_is_what_the_order_charges(self):
		ensure_fiscal_year()
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 3)]})
		update_quotation_address(self.address_payload())
		self.add_tax_to_cart()
		self.set_cod_fee(49.5)
		summary = get_checkout_summary(_get_cart_quotation())["cash_on_delivery"]

		initiate_checkout_with_mode(COD_PAYMENT_MODE)
		order_name = confirm_payment(_get_cart_quotation().name, payment_mode=COD_PAYMENT_MODE)["order_name"]

		frappe.set_user("Administrator")
		sales_order = frappe.get_doc("Sales Order", order_name)
		self.assertEqual(summary["cod_charge"], 49.5)
		# Rounding once after the fee, as the order does; rounding the goods first and adding 49.50 lands on .50.
		self.assertEqual(summary["total"], round(270 + 48.6 + summary["shipping"] + 49.5))
		self.assertEqual(summary["total"], sales_order.rounded_total)
		self.assertEqual(
			get_order_charge_lines(sales_order.name, sales_order.shipping_rule)["taxes"],
			[{"description": TAX_DESCRIPTION, "amount": 48.6}],
		)

	def test_a_pickup_summary_drops_the_charges_without_saving_that(self):
		self.set_store_pickup(1)
		warehouse = self.create_pickup_warehouse()
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 3)]})
		self.add_tax_to_cart()

		summary = update_quotation_address(self.pickup_payload(warehouse))["checkout_summary"]

		self.assertEqual(summary["taxes"], [])
		self.assertEqual(summary["total"], 270)
		self.assertIn(TAX_DESCRIPTION, [row.description for row in _get_cart_quotation().taxes])

	def test_switching_from_pickup_back_to_delivery_keeps_the_tax(self):
		self.set_store_pickup(1)
		warehouse = self.create_pickup_warehouse()
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 3)]})
		self.add_tax_to_cart()
		update_quotation_address(self.pickup_payload(warehouse))

		summary = update_quotation_address(self.address_payload())["checkout_summary"]

		self.assertEqual(summary["taxes"], [{"description": TAX_DESCRIPTION, "amount": 48.6}])
		self.assertIn(TAX_DESCRIPTION, [row.description for row in _get_cart_quotation().taxes])

	def test_opening_checkout_does_not_rewrite_a_cart_with_a_stale_delivery_option(self):
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 3)]})
		update_quotation_address(self.address_payload())
		quotation = _get_cart_quotation()
		quotation.custom_delivery_option = "ZZ Retired Courier"
		quotation.custom_delivery_charge = 40
		save_cart_quotation(quotation)
		before = _get_cart_quotation()

		context = frappe._dict()
		get_checkout_context(context)

		after = _get_cart_quotation()
		self.assertEqual(after.modified, before.modified)
		self.assertEqual(
			[(row.description, row.tax_amount) for row in after.taxes],
			[(row.description, row.tax_amount) for row in before.taxes],
		)
		self.assertEqual(context.checkout_summary["total"], after.rounded_total or after.grand_total)

	# -- stock ------------------------------------------------------------------------------------

	def test_a_cart_beyond_available_stock_is_refused(self):
		frappe.set_user(self.shopper)

		with self.assertRaises(frappe.ValidationError):
			generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 9999)]})

		self.assertFalse(frappe.get_all("Quotation", {"contact_email": self.shopper, "docstatus": 0}))

	def test_a_cart_within_available_stock_is_accepted(self):
		frappe.set_user(self.shopper)
		validate_stock_available([self.cart_line(self.discounted_item, IN_STOCK_QTY)])

		self.assertEqual(get_stock_shortfalls([self.cart_line(self.discounted_item, IN_STOCK_QTY)]), [])

	def test_the_shortfall_names_the_item_and_both_quantities(self):
		shortfalls = get_stock_shortfalls([self.cart_line(self.discounted_item, 9)])

		self.assertEqual(shortfalls, ["ZZ Cart Item - Requested: 9, In Stock: 4"])

	# -- pricing ----------------------------------------------------------------------------------

	def test_an_item_with_no_sale_row_falls_back_to_the_default_price(self):
		detail = get_detail_for_cart_items([self.cart_line(self.full_price_item, 1)])

		self.assertEqual(detail["stock_data"][self.full_price_item]["sale_price"], DEFAULT_RATE)
		self.assertEqual(detail["stock_data"][self.full_price_item]["default_price"], DEFAULT_RATE)

	def test_an_item_with_a_sale_row_keeps_its_sale_price(self):
		detail = get_detail_for_cart_items([self.cart_line(self.discounted_item, 1)])

		self.assertEqual(detail["stock_data"][self.discounted_item]["sale_price"], SALE_RATE)
		self.assertEqual(detail["stock_data"][self.discounted_item]["default_price"], DEFAULT_RATE)

	# -- store pickup -----------------------------------------------------------------------------

	def set_store_pickup(self, enabled: int):
		frappe.db.set_single_value("Commera Settings", "store_pickup_enabled", enabled)
		# A rolled-back Single stays in Redis and would leak the switch into later tests.
		self.addCleanup(frappe.clear_document_cache, "Commera Settings", "Commera Settings")

	def create_pickup_warehouse(self, allow_pickup: int = 1, with_address: bool = True) -> str:
		company = frappe.db.get_value("Warehouse", self.warehouse, "company")
		warehouse = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": f"ZZ Pickup {frappe.generate_hash(length=6)}",
				"company": company,
				"custom_store_pickup": allow_pickup,
			}
		).insert(ignore_permissions=True)
		if with_address:
			self.create_shop_address(warehouse.name)
		return warehouse.name

	def create_shop_address(
		self, warehouse: str, title: str = "ZZ Pickup Counter", location: str = ""
	) -> str:
		address = frappe.new_doc("Address")
		address.update(
			{
				"address_title": title,
				"address_type": "Shop",
				"address_line1": "1 Pickup Street",
				"city": "Riyadh",
				"country": COUNTRY,
				"custom_store_location": location,
			}
		)
		address.append("links", {"link_doctype": "Warehouse", "link_name": warehouse})
		return address.insert(ignore_permissions=True).name

	def pickup_payload(self, warehouse: str) -> dict:
		return {"is_store_pickup": True, "store_pickup_warehouse": warehouse}

	def test_store_pickup_is_off_on_a_fresh_install(self):
		field = frappe.get_meta("Commera Settings").get_field("store_pickup_enabled")

		self.assertEqual(field.default, "0")

	def test_pickup_is_refused_while_store_pickup_is_off(self):
		self.set_store_pickup(0)
		warehouse = self.create_pickup_warehouse()
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 1)]})

		with self.assertRaises(frappe.ValidationError):
			update_quotation_address(self.pickup_payload(warehouse))

		self.assertFalse(_get_cart_quotation().custom_is_store_pickup)

	def test_pickup_is_refused_at_a_warehouse_not_allowed_for_pickup(self):
		self.set_store_pickup(1)
		warehouse = self.create_pickup_warehouse(allow_pickup=0)
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 1)]})

		with self.assertRaises(frappe.ValidationError):
			update_quotation_address(self.pickup_payload(warehouse))

	def test_pickup_is_refused_at_a_warehouse_without_a_shop_address(self):
		self.set_store_pickup(1)
		warehouse = self.create_pickup_warehouse(with_address=False)
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 1)]})

		with self.assertRaises(frappe.ValidationError):
			update_quotation_address(self.pickup_payload(warehouse))

	def test_checkout_offers_only_pickup_warehouses_with_a_shop_address(self):
		with_address = self.create_pickup_warehouse()
		without_address = self.create_pickup_warehouse(with_address=False)

		offered = {option["warehouse_name"] for option in get_store_pickup_addresses()}

		self.assertIn(with_address, offered)
		self.assertNotIn(without_address, offered)

	def test_checkout_links_directions_to_the_pin(self):
		warehouse = self.create_pickup_warehouse(with_address=False)
		self.create_shop_address(warehouse, location=PIN_GEOJSON)

		option = next(
			option for option in get_store_pickup_addresses() if option["warehouse_name"] == warehouse
		)

		self.assertEqual(
			option["directions_url"], "https://www.google.com/maps/dir/?api=1&destination=24.7136,46.6753"
		)

	def test_the_most_recently_changed_shop_address_is_the_pickup_address(self):
		warehouse = self.create_pickup_warehouse(with_address=False)
		older = self.create_shop_address(warehouse, title="ZZ Older Counter")
		newer = self.create_shop_address(warehouse, title="ZZ Newer Counter")
		frappe.db.set_value("Address", older, "modified", "2020-01-01 00:00:00", update_modified=False)

		self.assertEqual(get_pickup_addresses([warehouse])[warehouse].name, newer)

	def test_shopper_picks_up_from_an_allowed_warehouse(self):
		self.set_store_pickup(1)
		warehouse = self.create_pickup_warehouse()
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 1)]})

		update_quotation_address(self.pickup_payload(warehouse))

		quotation = _get_cart_quotation()
		self.assertTrue(quotation.custom_is_store_pickup)
		self.assertEqual(quotation.custom_store, warehouse)

	def test_a_pickup_cart_cannot_pay_once_store_pickup_is_switched_off(self):
		self.set_store_pickup(1)
		warehouse = self.create_pickup_warehouse()
		frappe.set_user(self.shopper)
		generate_quotation_for_cart({"items": [self.cart_line(self.discounted_item, 1)]})
		update_quotation_address(self.pickup_payload(warehouse))

		self.set_store_pickup(0)

		with self.assertRaises(frappe.ValidationError):
			update_delivery_charges(_get_cart_quotation())
