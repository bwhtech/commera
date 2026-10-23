import random

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.payments import add_customer_address
from commera.api.storefront import account
from commera.core import get_party
from commera.order_access import OWNER_ACCESS, get_order_access, get_shopper_order_condition
from commera.sdk.types import CustomerAddress, CustomerProfile, ShopperOrder, ShopperOrderPage
from commera.tests.test_admin_orders import make_test_sales_order
from commera.tests.test_order_access import make_website_user
from commera.utils import validate_document_access
from commera.www.account.orders.index import get_orders_list

ADDRESS = {
	"address_type": "Shipping",
	"address_line1": "12 Harbour Road",
	"city": "Kochi",
	"country": "India",
	"phone": "9876543210",
}


class TestStorefrontAccount(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		self.shopper = make_website_user()
		self.other = make_website_user()

	def assert_shape(self, result: dict, shape):
		self.assertEqual(set(result), shape.__required_keys__ | shape.__optional_keys__)

	def test_a_guest_is_refused(self):
		frappe.set_user("Guest")
		for method in (account.get_profile, account.list_addresses, account.list_orders):
			with self.subTest(method.__name__), self.assertRaises(frappe.PermissionError):
				method()

	def test_a_shopper_reads_and_updates_their_profile(self):
		frappe.set_user(self.shopper)

		# User.mobile_no is unique across the site.
		phone = f"98{random.randrange(10**8):08d}"
		profile = account.update_profile("Asha", "Menon", phone)

		self.assert_shape(profile, CustomerProfile)
		self.assertEqual(
			(profile["email"], profile["full_name"], profile["phone"]),
			(self.shopper, "Asha Menon", phone),
		)
		self.assertEqual(account.update_profile("Asha Rani")["last_name"], "Menon")
		with self.assertRaises(frappe.ValidationError):
			account.update_profile(" ")

	def test_listing_addresses_creates_no_customer(self):
		frappe.set_user(self.shopper)

		self.assertEqual(account.list_addresses(), [])
		self.assertFalse(frappe.db.exists("Portal User", {"user": self.shopper}))

	def test_a_shopper_adds_updates_and_deletes_their_address(self):
		frappe.set_user(self.shopper)

		added = account.save_address(ADDRESS)
		updated = account.save_address({"name": added["name"], "city": "Kollam"})

		self.assert_shape(added, CustomerAddress)
		self.assertEqual(updated["city"], "Kollam")
		self.assertFalse(updated["is_primary_address"])
		self.assertEqual([address["name"] for address in account.list_addresses()], [added["name"]])
		account.delete_address(added["name"])
		self.assertEqual(account.list_addresses(), [])

	def test_a_shopper_cannot_touch_another_shoppers_address(self):
		frappe.set_user(self.other)
		address = account.save_address(ADDRESS)["name"]
		frappe.set_user(self.shopper)

		with self.assertRaises(frappe.DoesNotExistError):
			account.save_address({"name": address, "city": "Elsewhere"})
		with self.assertRaises(frappe.ValidationError):
			account.delete_address(address)
		self.assertNotIn(address, [row["name"] for row in account.list_addresses()])
		self.assertEqual(frappe.db.get_value("Address", address, "city"), ADDRESS["city"])

	def test_a_guest_checkout_address_on_the_shoppers_customer_is_theirs(self):
		frappe.set_user(self.shopper)
		customer = get_party(self.shopper).name
		frappe.set_user(self.other)
		other_customer = get_party(self.other).name
		frappe.set_user("Administrator")
		guest_address = add_customer_address(customer, {**ADDRESS, "address_line1": "Guest checkout"})
		guest_address.db_set("owner", "Guest")
		elsewhere = add_customer_address(other_customer, {**ADDRESS, "address_line1": "Elsewhere"})
		elsewhere.db_set("owner", self.shopper)
		frappe.set_user(self.shopper)

		self.assertEqual(
			account.save_address({"name": guest_address.name, "city": "Kollam"})["city"], "Kollam"
		)
		account.delete_address(guest_address.name)
		self.assertFalse(frappe.db.exists("Address", guest_address.name))
		with self.assertRaises(frappe.DoesNotExistError):
			account.save_address({"name": elsewhere.name, "city": "Kollam"})
		with self.assertRaises(frappe.ValidationError):
			account.delete_address(elsewhere.name)

	def test_an_address_type_other_than_billing_or_shipping_is_refused(self):
		frappe.set_user(self.shopper)

		with self.assertRaisesRegex(frappe.ValidationError, "Address type must be one of"):
			account.save_address({**ADDRESS, "address_type": "Office"})
		self.assertEqual(account.save_address({**ADDRESS, "address_type": None})["address_type"], "Shipping")

	def test_a_guest_order_placed_with_the_shoppers_email_is_theirs_everywhere(self):
		guest = self.make_order(contact_email=self.shopper, guest_cart=True)
		other_email = self.make_order(contact_email=self.other, guest_cart=True)
		signed_in = self.make_order(owner=self.other, contact_email=self.shopper)
		# Checkout lowercases contact_email; the User keeps the case the shopper signed up with.
		frappe.db.set_value("User", self.shopper, "email", self.shopper.upper())
		frappe.set_user(self.shopper)

		self.assertEqual(get_order_access(guest), OWNER_ACCESS)
		self.assertIsNone(get_order_access(other_email))
		self.assertIsNone(get_order_access(signed_in))
		_, listed = get_orders_list([guest, other_email, signed_in])
		self.assertEqual([order.name for order in listed], [guest])
		self.assertEqual([order["name"] for order in account.list_orders()["orders"]], [guest])

	def test_a_guest_order_placed_with_the_shoppers_email_opens_its_invoice_and_returns(self):
		guest = self.make_order(contact_email=self.shopper, guest_cart=True)
		other_email = self.make_order(contact_email=self.other, guest_cart=True)
		frappe.set_user(self.shopper)

		self.assertEqual(validate_document_access("Sales Order", guest).name, guest)
		with self.assertRaises(frappe.PermissionError):
			validate_document_access("Sales Order", other_email)

	def test_a_guest_session_matches_no_order(self):
		self.make_order(owner="Guest", contact_email=self.shopper, guest_cart=True)
		sales_order = frappe.qb.DocType("Sales Order")
		matched = (
			frappe.qb.from_(sales_order)
			.select(sales_order.name)
			.where(get_shopper_order_condition("Guest"))
			.run()
		)
		self.assertEqual(matched, ())

	def test_orders_hold_the_shoppers_own_and_their_guest_orders_only(self):
		own = self.make_order(owner=self.shopper)
		guest = self.make_order(contact_email=self.shopper, guest_cart=True)
		self.make_order(owner=self.other)
		# Booked to the shopper's email by a signed-in account, not by a guest: not the shopper's.
		self.make_order(owner=self.other, contact_email=self.shopper)
		frappe.set_user(self.shopper)

		page = account.list_orders(page_size=1)

		self.assert_shape(page, ShopperOrderPage)
		self.assertEqual((page["total"], page["page_size"]), (2, 1))
		names = {page["orders"][0]["name"], account.list_orders(page=2, page_size=1)["orders"][0]["name"]}
		self.assertEqual(names, {own, guest})
		self.assert_shape(account.get_order(guest), ShopperOrder)

	def test_a_shopper_cannot_read_another_shoppers_order(self):
		order = self.make_order(owner=self.other)
		frappe.set_user(self.shopper)

		with self.assertRaises(frappe.DoesNotExistError):
			account.get_order(order)

	def make_order(self, owner: str = "Administrator", contact_email=None, guest_cart=False) -> str:
		sales_order = make_test_sales_order()
		sales_order.db_set({"owner": owner, "contact_email": contact_email})
		# The Jinja order list reads only lines whose item has a Size attribute.
		frappe.get_doc(
			{
				"doctype": "Item Variant Attribute",
				"parent": sales_order.items[0].item_code,
				"parenttype": "Item",
				"parentfield": "attributes",
				"attribute": "Size",
				"attribute_value": "M",
			}
		).db_insert()
		if guest_cart:
			frappe.db.set_value(
				"Sales Order Item",
				sales_order.items[0].name,
				"prevdoc_docname",
				self.make_guest_cart(sales_order),
			)
		return sales_order.name

	def make_guest_cart(self, sales_order) -> str:
		return (
			frappe.get_doc(
				{
					"doctype": "Quotation",
					"quotation_to": "Customer",
					"party_name": sales_order.customer,
					"company": sales_order.company,
					"currency": sales_order.currency,
					"conversion_rate": 1,
					"order_type": "Shopping Cart",
					"custom_guest_cart_key": frappe.generate_hash(length=64),
					"items": [{"item_code": sales_order.items[0].item_code, "qty": 1, "rate": 10}],
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
