import frappe


def on_trash(doc, method=None):
	frappe.db.set_value("Storefront Analytics Event", {"order_id": doc.name}, "order_id", None)
