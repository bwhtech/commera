import frappe
from frappe.utils.data import cint, cstr, flt
from frappe.utils.password import get_decrypted_password

TELR_GATEWAY = "Telr"

# Telr Payment Request field -> Gateway Payment Request field; everything else is already named the same.
FIELD_MAP = {
	"telr_order_ref": "order_ref",
	"telr_order_url": "order_url",
	"transaction_reference": "gateway_transaction_ref",
}
COPIED_FIELDS = (
	"ref_doctype",
	"ref_docname",
	"status",
	"amount",
	"currency_code",
	"customer_ref",
	"customer_email",
	"customer_phone",
	"customer_address",
	"customer_forenames",
	"customer_surname",
	"refund_amount",
)


def execute():
	"""Move the retired Telr doctypes onto the gateway doctypes, carrying settings and the refund ledger."""
	add_gateway_profile()
	migrate_settings()
	migrate_payment_requests()
	drop_retired_doctypes()


def add_gateway_profile():
	if frappe.db.exists("Payment Gateway Profile", TELR_GATEWAY):
		return
	frappe.get_doc(
		{
			"doctype": "Payment Gateway Profile",
			"name": TELR_GATEWAY,
			"gateway_settings": "Telr Gateway Settings",
			"enabled": telr_was_enabled(),
		}
	).insert(ignore_permissions=True)


def get_retired_single_value(doctype: str, field: str):
	# tabSingles has no `creation` column, so the default order_by has to be suppressed.
	return frappe.db.get_value("Singles", {"doctype": doctype, "field": field}, "value", order_by=None)


def telr_was_enabled() -> int:
	# The field is gone from the meta by the time this runs, so the value comes off the Singles table.
	return cint(get_retired_single_value("Commera Settings", "telr_enabled"))


def migrate_settings():
	if not frappe.db.exists("DocType", "Telr Settings"):
		return

	target = frappe.get_single("Telr Gateway Settings")
	if target.store_id:
		return

	# The old controller module is gone, so the retired Single is read off Singles, not get_single().
	for field in ("test_mode", "store_id", "currency", "authorised_url", "declined_url", "cancelled_url"):
		target.set(field, get_retired_single_value("Telr Settings", field))
	for field in ("auth_key", "remote_auth_key"):
		target.set(
			field, get_decrypted_password("Telr Settings", "Telr Settings", field, raise_exception=False)
		)
	target.enabled = telr_was_enabled()
	target.flags.ignore_mandatory = True
	target.save(ignore_permissions=True)


def migrate_payment_requests():
	if not frappe.db.exists("DocType", "Telr Payment Request"):
		return

	# Telr Payment Request is autoincrement-named, so `name` comes back as an int.
	existing_refs = set(frappe.get_all("Gateway Payment Request", pluck="order_ref"))
	for row in frappe.get_all(
		"Telr Payment Request",
		fields=["name", *COPIED_FIELDS, *FIELD_MAP.keys()],
	):
		order_ref = cstr(row.telr_order_ref) or f"telr-legacy-{cstr(row.name)}"
		if order_ref in existing_refs:
			continue

		target = frappe.new_doc("Gateway Payment Request")
		target.gateway = TELR_GATEWAY
		for field in COPIED_FIELDS:
			target.set(field, row.get(field))
		for source_field, target_field in FIELD_MAP.items():
			target.set(target_field, cstr(row.get(source_field)) or None)
		target.order_ref = order_ref
		target.refund_amount = flt(row.refund_amount)
		# The gateway session already exists; before_save must not open a second one.
		target.flags.ignore_mandatory = True
		target.insert(ignore_permissions=True)
		existing_refs.add(order_ref)


def drop_retired_doctypes():
	for doctype in ("Telr Payment Request", "Telr Settings"):
		# DocType Links survive the delete and collide when customizations sync later in the same migrate.
		frappe.db.delete("DocType Link", {"link_doctype": doctype})
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_missing=True)
