# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from commera.webhooks import clear_subscriptions


class CommeraWebhook(Document):
	def validate(self):
		events = [row.event for row in self.events]
		if len(events) != len(set(events)):
			frappe.throw(_("Each event can only be listed once."))
		if not self.url.startswith(("https://", "http://")):
			frappe.throw(_("The URL must start with https:// or http://."))

	def on_update(self):
		clear_subscriptions()

	def on_trash(self):
		clear_subscriptions()
