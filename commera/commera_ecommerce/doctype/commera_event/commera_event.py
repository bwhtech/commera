# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.query_builder import Interval
from frappe.query_builder.functions import Now
from pypika.terms import ExistsCriterion

CLEARABLE_EVENTS = ("product_updated", "inventory_changed")


class CommeraEvent(Document):
	@staticmethod
	def clear_old_logs(days=14):
		"""Called daily by Log Settings. Never touches order events: their row is what stops one firing twice."""
		commera_event = frappe.qb.DocType("Commera Event")
		delivery = frappe.qb.DocType("Commera Event Delivery")
		queued_delivery = (
			frappe.qb.from_(delivery)
			.select(delivery.name)
			.where((delivery.parent == commera_event.name) & delivery.status.isin(("Queued", "Running")))
		)
		old_events = (
			frappe.qb.from_(commera_event)
			.select(commera_event.name)
			.where(
				commera_event.event.isin(CLEARABLE_EVENTS)
				& (commera_event.creation < Now() - Interval(days=days))
				& ExistsCriterion(queued_delivery).negate()
			)
			.limit(1000)
		)
		while event_names := old_events.run(pluck=True):
			frappe.db.delete("Commera Event Delivery", {"parent": ("in", event_names)})
			frappe.db.delete("Commera Event", {"name": ("in", event_names)})
