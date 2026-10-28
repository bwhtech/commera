# Copyright (c) 2026, Build With Hussain and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from commera.shipping.base_class import ShippingProviderBase
from commera.shipping.utils import get_available_shipping_providers


class ShippingProviderProfile(Document):
	def validate(self):
		self.validate_provider_settings_implement_contract()

	def validate_provider_settings_implement_contract(self):
		controller = frappe.get_single(self.provider_settings)
		if not isinstance(controller, ShippingProviderBase):
			frappe.throw(
				_("{0} does not implement the shipping provider contract").format(
					frappe.bold(self.provider_settings)
				)
			)

	def on_update(self):
		get_available_shipping_providers.clear_cache()

	def on_trash(self):
		get_available_shipping_providers.clear_cache()

	def get_controller(self) -> ShippingProviderBase:
		return frappe.get_single(self.provider_settings)
