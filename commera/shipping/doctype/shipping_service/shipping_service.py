# Copyright (c) 2026, Build With Hussain and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.data import cstr, flt

from commera.shipping.pricing import get_enabled_services


class ShippingService(Document):
	def validate(self):
		self.validate_bookable()

	def validate_bookable(self):
		# Catch gaps at config time, not on a paid order. A service with no provider is delivered by
		# the store itself and has nothing to book.
		if not self.enabled or not self.provider:
			return
		if not self.service_code:
			frappe.throw(
				_(
					"Set a Service Code on {0} before enabling it — a label cannot be booked without one."
				).format(frappe.bold(self.title))
			)
		if not frappe.get_cached_value("Shipping Provider Profile", self.provider, "enabled"):
			frappe.throw(
				_("Shipping Provider Profile {0} is disabled, so {1} cannot be offered at checkout.").format(
					frappe.bold(self.provider), frappe.bold(self.title)
				)
			)

	def on_update(self):
		get_enabled_services.clear_cache()

	def on_trash(self):
		get_enabled_services.clear_cache()


@frappe.whitelist()
def create_shipping_services(provider: str, selections: list | str, default_rate: float = 0) -> list[str]:
	"""Create Shipping Services from the importer selections. `default_rate` seeds the Backup Charge;
	codes already imported for this provider are skipped."""
	frappe.only_for("System Manager")
	selections = frappe.parse_json(selections)
	if not selections:
		frappe.throw(_("Select at least one carrier service to import."))

	existing_codes = {
		service.service_code
		for service in frappe.get_all(
			"Shipping Service", filters={"provider": provider}, fields=["service_code"]
		)
	}
	# Title is the autoname, so a clash is a save error rather than a second row.
	used_titles = set(frappe.get_all("Shipping Service", pluck="title"))

	created, skipped = [], []
	for selection in selections:
		service_code = cstr(selection.get("service_code"))
		service_name = cstr(selection.get("service_name")) or service_code
		carrier = cstr(selection.get("carrier"))
		if not service_code:
			continue
		if service_code in existing_codes:
			skipped.append(service_name)
			continue

		title = get_unique_title(service_name, carrier, used_titles)
		service = frappe.get_doc(
			{
				"doctype": "Shipping Service",
				"enabled": 1,
				"title": title,
				"provider": provider,
				"service_code": service_code,
				"carrier": carrier,
				"backup_charge": flt(default_rate),
			}
		).insert()

		existing_codes.add(service_code)
		used_titles.add(title)
		created.append(service.name)

	if skipped:
		frappe.msgprint(
			_("Skipped {0} service(s) already imported: {1}").format(len(skipped), ", ".join(skipped)),
			indicator="orange",
		)
	return created


def get_unique_title(service_name: str, carrier: str, used_titles: set) -> str:
	"""Two carriers routinely sell a service called "Express", and Title is this doctype's autoname, so an
	imported row is suffixed with its carrier (then a counter) rather than failing the whole import."""
	if service_name not in used_titles:
		return service_name

	with_carrier = f"{service_name} ({carrier})" if carrier else service_name
	if with_carrier not in used_titles:
		return with_carrier

	counter = 2
	while f"{with_carrier} {counter}" in used_titles:
		counter += 1
	return f"{with_carrier} {counter}"
