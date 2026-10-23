import frappe

DOCTYPES = ("Quotation Item", "Sales Order Item", "Sales Invoice Item")
OLD_FIELDNAME = "custom_discount_code"
NEW_FIELDNAME = "custom_discount"


def execute():
	# Before the fixture sync, which would otherwise add an empty custom_discount next to the filled old column.
	custom_field = frappe.qb.DocType("Custom Field")
	for doctype in DOCTYPES:
		old_name, new_name = f"{doctype}-{OLD_FIELDNAME}", f"{doctype}-{NEW_FIELDNAME}"
		if frappe.db.exists("Custom Field", old_name) and not frappe.db.exists("Custom Field", new_name):
			(
				frappe.qb.update(custom_field)
				.set(custom_field.name, new_name)
				.set(custom_field.fieldname, NEW_FIELDNAME)
				.where(custom_field.name == old_name)
			).run()
		if frappe.db.has_column(doctype, OLD_FIELDNAME) and not frappe.db.has_column(doctype, NEW_FIELDNAME):
			frappe.db.rename_column(doctype, OLD_FIELDNAME, NEW_FIELDNAME)
		frappe.clear_cache(doctype=doctype)
