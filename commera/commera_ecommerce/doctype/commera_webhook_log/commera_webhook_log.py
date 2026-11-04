# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.query_builder import Interval
from frappe.query_builder.functions import Now


class CommeraWebhookLog(Document):
	@staticmethod
	def clear_old_logs(days=30):
		"""Called daily by Log Settings. Keeps Retrying rows, which a pending retry still updates."""
		log = frappe.qb.DocType("Commera Webhook Log")
		frappe.db.delete(
			log, filters=(log.creation < (Now() - Interval(days=days))) & (log.status != "Retrying")
		)
