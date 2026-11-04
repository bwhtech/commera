from commera.shipping.shipment import (
	get_erpnext_status,
	sync_erpnext_status,
	validate_carrier_cancel,
	validate_tracking_url,
)
from commera.utils import update_so_status_from_related_doc


def validate(doc, method=None):
	validate_tracking_url(doc)
	sync_erpnext_status(doc)


def before_update_after_submit(doc, method=None):
	validate_tracking_url(doc)
	sync_erpnext_status(doc)


def on_update(doc, method=None):
	update_so_status_from_related_doc(doc, method)


def on_submit(doc, method=None):
	doc.db_set("status", get_erpnext_status(doc))
	update_so_status_from_related_doc(doc, method)


def on_update_after_submit(doc, method=None):
	update_so_status_from_related_doc(doc, method)


def before_cancel(doc, method=None):
	validate_carrier_cancel(doc)


def on_cancel(doc, method=None):
	update_so_status_from_related_doc(doc, method)
