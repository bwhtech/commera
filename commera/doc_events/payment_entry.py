from bwh_payments_core.engine.payment_request import refund_on_payment_entry

from commera.plugin_events import on_payment_entry_submit


def on_submit(doc, method=None):
	refund_on_payment_entry(doc)
	on_payment_entry_submit(doc)
