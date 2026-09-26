# Copyright (c) 2026, company@bwhstudios.com and Contributors

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.payments import add_billing_address, add_shipping_address

COMPANY = "Lifestyle Demo"
ITEM_GROUP = "Interior Accessories"
CURRENCY = "INR"
PRICE_LIST = "ZZ Checkout Address SAR Selling"
ITEM_RATE = 120.0
COUNTRY = "Saudi Arabia"


class TestCheckoutAddress(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ensure_price_list()

	def setUp(self):
		self.customer = self.create_customer()
		self.item_code = self.create_item()

	# -- fixtures ---------------------------------------------------------------------------------

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

	def create_customer(self):
		return (
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": f"ZZ Address Customer {frappe.generate_hash(length=8)}",
					"customer_type": "Individual",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def create_item(self):
		item_code = f"ZZ-ADDRESS-{frappe.generate_hash(length=8)}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": "ZZ Checkout Address Item",
				"item_group": ITEM_GROUP,
				"stock_uom": "Nos",
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

	def checkout_payload(self):
		return {
			"billing_address": {
				"full_address": "1 Billing Street",
				"city": "Riyadh",
				"state": "Riyadh Province",
				"country": COUNTRY,
				"phone_number": "+966500000001",
				"email": "zz_address@example.com",
				"first_name": "ZZ",
				"last_name": "Shopper",
			},
			"shipping_address": {
				"full_address": "2 Shipping Street",
				"city": "Jeddah",
				"state": "Makkah Province",
				"country": COUNTRY,
				"phone_number": "+966500000002",
				"email": "zz_address@example.com",
				"first_name": "ZZ",
				"last_name": "Shopper",
			},
		}

	def create_cart_quotation(self, customer_address, shipping_address_name):
		quotation = frappe.new_doc("Quotation")
		quotation.update(
			{
				"quotation_to": "Customer",
				"party_name": self.customer,
				"company": COMPANY,
				"order_type": "Shopping Cart",
				"currency": CURRENCY,
				"conversion_rate": 1,
				"selling_price_list": PRICE_LIST,
				"price_list_currency": CURRENCY,
				"plc_conversion_rate": 1,
				"customer_address": customer_address,
				"shipping_address_name": shipping_address_name,
				"items": [{"item_code": self.item_code, "qty": 1}],
			}
		)
		quotation.flags.ignore_permissions = True
		quotation.insert()
		return quotation

	def customer_links_of(self, address_name):
		return frappe.get_all(
			"Dynamic Link",
			filters={"parenttype": "Address", "parent": address_name, "link_doctype": "Customer"},
			pluck="link_name",
		)

	# -- tests ------------------------------------------------------------------------------------

	def test_billing_address_is_linked_to_the_customer(self):
		address = add_billing_address(self.customer, self.checkout_payload())
		self.assertEqual(self.customer_links_of(address.name), [self.customer])
		self.assertEqual(frappe.db.get_value("Address", address.name, "state"), "Riyadh Province")

	def test_shipping_address_is_linked_to_the_customer(self):
		address = add_shipping_address(self.customer, self.checkout_payload())
		self.assertEqual(self.customer_links_of(address.name), [self.customer])
		self.assertEqual(frappe.db.get_value("Address", address.name, "state"), "Makkah Province")

	def test_quotation_accepts_checkout_addresses(self):
		payload = self.checkout_payload()
		billing_address = add_billing_address(self.customer, payload)
		shipping_address = add_shipping_address(self.customer, payload)

		quotation = self.create_cart_quotation(billing_address.name, shipping_address.name)

		self.assertEqual(quotation.customer_address, billing_address.name)
		self.assertEqual(quotation.shipping_address_name, shipping_address.name)

	def test_quotation_rejects_an_unlinked_address(self):
		"""Guards the assertions above: without the link, erpnext refuses the Quotation."""
		unlinked_address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": f"ZZ Unlinked {frappe.generate_hash(length=8)}",
				"address_type": "Billing",
				"address_line1": "3 Orphan Street",
				"city": "Riyadh",
				"country": COUNTRY,
			}
		).insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			self.create_cart_quotation(unlinked_address.name, unlinked_address.name)

	def test_a_retried_address_save_reuses_the_saved_address(self):
		first_attempt = add_billing_address(self.customer, self.checkout_payload())
		retry = add_billing_address(self.customer, self.checkout_payload())

		self.assertEqual(retry.name, first_attempt.name)
		self.assertEqual(self.addresses_of_customer(), [first_attempt.name])

	def test_a_different_address_is_saved_as_a_new_one(self):
		first_address = add_billing_address(self.customer, self.checkout_payload())
		payload = self.checkout_payload()
		payload["billing_address"]["full_address"] = "9 Other Street"

		second_address = add_billing_address(self.customer, payload)

		self.assertNotEqual(second_address.name, first_address.name)

	def test_another_customers_identical_address_is_not_reused(self):
		other_customer_address = add_billing_address(self.create_customer(), self.checkout_payload())

		own_address = add_billing_address(self.customer, self.checkout_payload())

		self.assertNotEqual(own_address.name, other_customer_address.name)
		self.assertEqual(self.customer_links_of(own_address.name), [self.customer])

	def test_a_disabled_address_is_not_reused(self):
		disabled_address = add_billing_address(self.customer, self.checkout_payload())
		frappe.db.set_value("Address", disabled_address.name, "disabled", 1)

		new_address = add_billing_address(self.customer, self.checkout_payload())

		self.assertNotEqual(new_address.name, disabled_address.name)
		self.assertFalse(new_address.disabled)

	def addresses_of_customer(self):
		return frappe.get_all(
			"Dynamic Link",
			filters={"parenttype": "Address", "link_doctype": "Customer", "link_name": self.customer},
			pluck="parent",
		)

	def test_address_without_a_party_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			add_billing_address(None, self.checkout_payload())
		with self.assertRaises(frappe.ValidationError):
			add_shipping_address(None, self.checkout_payload())
