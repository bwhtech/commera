import frappe

from commera.utils import update_so_status_from_related_doc


def on_trash(doc, method=None):
	frappe.db.set_value("Storefront Analytics Event", {"order_id": doc.name}, "order_id", None)


def on_update_after_submit(doc, method=None):
	update_so_status_from_related_doc(doc, method)


def on_change(doc, method=None):
	if doc.has_value_changed("status") and "Closed" in (doc.status, doc.get_value_before_save("status")):
		update_so_status_from_related_doc(doc, method)
