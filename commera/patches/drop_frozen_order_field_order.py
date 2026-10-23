import hashlib

import frappe

# sha256 of each value the commera fixtures used to ship, so a site's own customization is left alone.
SHIPPED_LAYOUT_SETTERS = {
	"Sales Order-main-field_order": "cba8f8616496e2dfda61f4474996c43910b7df240e55dbfa8c1398c2abe72fcb",
	"Sales Order-main-links_order": "a2d48f3a6831935f12674f0eac058d148b0f65bb9fe0dae96120259a2d141adc",
	"Quotation-main-field_order": "fc32caf2a4beb9a801c80a1cf79da5535bda0c0e2ac3b9254b5001c8ebd85ae6",
}


def execute():
	drop_shipped_setters(SHIPPED_LAYOUT_SETTERS)


def drop_shipped_setters(shipped_setters):
	setters = frappe.get_all(
		"Property Setter",
		filters={"name": ["in", list(shipped_setters)]},
		fields=["name", "doc_type", "value"],
	)
	for setter in setters:
		if hashlib.sha256((setter.value or "").encode()).hexdigest() != shipped_setters[setter.name]:
			continue
		frappe.delete_doc("Property Setter", setter.name, ignore_permissions=True, force=True)
		frappe.clear_cache(doctype=setter.doc_type)
