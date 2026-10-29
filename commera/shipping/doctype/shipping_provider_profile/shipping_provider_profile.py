# Copyright (c) 2026, Build With Hussain and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from commera.shipping.base_class import ShippingProviderBase
from commera.shipping.providers import get_available_shipping_providers, get_provider, get_provider_class
from commera.shipping.rates import clear_rates_cache


class ShippingProviderProfile(Document):
	def validate(self):
		# A disabled profile may point at a removed app; migrate asks the operator to disable exactly those.
		if self.enabled:
			get_provider_class(self.provider_settings)

	def on_update(self):
		get_available_shipping_providers.clear_cache()
		clear_rates_cache(self.name)

	def on_trash(self):
		get_available_shipping_providers.clear_cache()
		clear_rates_cache(self.name)

	def get_controller(self) -> ShippingProviderBase:
		return get_provider(self.name)
