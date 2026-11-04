# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from bwh_payments_core.contract import PaymentGatewayBase
from frappe import _
from frappe.model.document import Document

from commera.payment_gateways.connectors import clear_available_payment_modes


class PaymentGatewayProfile(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		enabled: DF.Check
		gateway_settings: DF.Link | None
	# end: auto-generated types

	def validate(self):
		self.validate_gateway_settings_implement_contract()

	def validate_gateway_settings_implement_contract(self):
		if not self.gateway_settings:
			return
		if not isinstance(frappe.get_single(self.gateway_settings), PaymentGatewayBase):
			frappe.throw(
				_("{0} does not implement the payment gateway contract").format(
					frappe.bold(self.gateway_settings)
				)
			)

	def on_update(self):
		clear_available_payment_modes()

	def on_trash(self):
		clear_available_payment_modes()

	def after_rename(self, old_name: str, new_name: str, merge: bool = False):
		clear_available_payment_modes()

	def get_controller(self) -> PaymentGatewayBase:
		return frappe.get_single(self.gateway_settings)
