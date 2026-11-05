# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from commera.webhooks import LOG_DOCTYPE, clear_subscriptions, fail_retrying_logs, get_url_error


class CommeraWebhook(Document):
	def before_insert(self):
		if not self.secret:
			self.secret = generate_secret()

	def validate(self):
		events = [row.event for row in self.events]
		if not events:
			frappe.throw(_("Choose at least one event."))
		if len(events) != len(set(events)):
			frappe.throw(_("Each event can only be listed once."))
		if self.has_value_changed("url") and (error := get_url_error(self.url)):
			frappe.throw(error)
		if self.enabled and self.has_value_changed("enabled") and not self.is_new():
			self.reset_failures()

	def reset_failures(self):
		self.auto_disabled_at = None
		self.failed_attempts = 0
		self.failure_window_started_at = None

	def on_update(self):
		if not self.enabled and self.has_value_changed("enabled"):
			fail_retrying_logs(self.name)
		clear_subscriptions()

	def on_trash(self):
		frappe.db.delete(LOG_DOCTYPE, {"webhook": self.name})
		clear_subscriptions()


def generate_secret() -> str:
	return "whsec_" + frappe.generate_hash(length=32)
