import frappe
from frappe import _
from frappe.utils import cstr

from commera.commera_ecommerce.doctype.shopify_record_link.shopify_record_link import get_link, save_link
from commera.core import _get_default_territory, get_customer_contact, get_default_customer_group
from commera.shopify.bulk import get_children
from commera.shopify.importers.base import CREATED, SKIPPED, UPDATED, ResourceImporter, to_system_datetime
from commera.shopify.queries import CUSTOMER_QUERIES


class CustomerImporter(ResourceImporter):
	"""No User is made, so no email goes out. A shopper who signs in with the same email is linked to
	this Customer through the Contact."""

	resource = "Customers"
	queries = CUSTOMER_QUERIES

	def get_title(self, record: dict) -> str:
		return record.get("displayName") or get_email(record) or record.get("id")

	def import_record(self, customer: dict) -> str:
		link = get_link(customer["id"])
		if link and self.is_unchanged(link, customer):
			return SKIPPED

		email = get_email(customer)
		if link:
			customer_name, outcome = link.reference_name, UPDATED
		elif email and (existing := get_customer_contact(email)):
			customer_name, outcome = existing[0], UPDATED
		else:
			customer_name, outcome = self.create_customer(customer, email), CREATED

		if customer.get("note"):
			frappe.db.set_value("Customer", customer_name, "customer_details", customer["note"])
		self.add_addresses(customer, customer_name)
		save_link(
			customer["id"],
			self.resource,
			"Customer",
			customer_name,
			to_system_datetime(customer.get("updatedAt")),
		)
		return outcome

	def create_customer(self, customer: dict, email: str | None) -> str:
		phone = get_phone(customer)
		if not email and not phone:
			frappe.throw(_("The customer has no email and no phone."))

		full_name = cstr(customer.get("displayName")).strip() or email or phone
		customer_doc = frappe.new_doc("Customer")
		customer_doc.update(
			{
				"customer_name": full_name,
				"customer_type": "Individual",
				"customer_group": get_default_customer_group(),
				"territory": _get_default_territory(),
			}
		)
		customer_doc.flags.ignore_mandatory = True
		customer_doc.insert(ignore_permissions=True)

		contact = frappe.new_doc("Contact")
		contact.first_name = cstr(customer.get("firstName")).strip() or full_name
		contact.last_name = cstr(customer.get("lastName")).strip()
		if email:
			contact.append("email_ids", {"email_id": email, "is_primary": 1})
		if phone:
			contact.append("phone_nos", {"phone": phone, "is_primary_mobile_no": 1})
		contact.append("links", {"link_doctype": "Customer", "link_name": customer_doc.name})
		contact.flags.ignore_mandatory = True
		contact.insert(ignore_permissions=True)
		return customer_doc.name

	def add_addresses(self, customer: dict, customer_name: str) -> None:
		existing = {
			(cstr(row.address_line1).casefold(), cstr(row.pincode).casefold())
			for row in frappe.get_all(
				"Address",
				filters=[
					["Dynamic Link", "link_doctype", "=", "Customer"],
					["Dynamic Link", "link_name", "=", customer_name],
				],
				fields=["address_line1", "pincode"],
			)
		}
		default_id = (customer.get("defaultAddress") or {}).get("id")
		for address in get_addresses(customer):
			key = (cstr(address.get("address1")).casefold(), cstr(address.get("zip")).casefold())
			if not address.get("address1") or key in existing:
				continue
			insert_address(address, customer_name, bool(default_id) and address.get("id") == default_id)
			existing.add(key)


def insert_address(address: dict, customer_name: str, is_default: bool) -> None:
	country = frappe.db.get_value("Country", {"code": cstr(address.get("countryCodeV2")).lower()})
	address_doc = frappe.new_doc("Address")
	address_doc.update(
		{
			"address_title": customer_name,
			"address_type": "Shipping",
			"address_line1": address.get("address1"),
			"address_line2": address.get("address2"),
			"city": address.get("city") or "-",
			"state": address.get("province"),
			"pincode": address.get("zip"),
			"country": country or frappe.db.get_default("country"),
			"phone": address.get("phone"),
			"is_primary_address": int(is_default),
			"is_shipping_address": int(is_default),
		}
	)
	address_doc.append("links", {"link_doctype": "Customer", "link_name": customer_name})
	address_doc.flags.ignore_mandatory = True
	address_doc.insert(ignore_permissions=True)


def get_addresses(customer: dict) -> list[dict]:
	"""addressesV2 arrives as child lines of the bulk file. The older addresses list arrives inline."""
	return get_children(customer, "MailingAddress") or customer.get("addresses") or []


def get_email(customer: dict) -> str | None:
	email = (customer.get("defaultEmailAddress") or {}).get("emailAddress") or customer.get("email")
	return cstr(email).strip().lower() or None


def get_phone(customer: dict) -> str | None:
	phone = (customer.get("defaultPhoneNumber") or {}).get("phoneNumber") or customer.get("phone")
	return cstr(phone).strip() or None
