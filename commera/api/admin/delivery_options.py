# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""The Delivery Options screen: the Shipping Services a shopper picks between at checkout.
This module is only the dashboard's way into the doctype."""

import frappe
from frappe.utils.data import cint, cstr

from commera.api.admin.docfields import (
	build_field_groups,
	get_editable_docfields,
	get_linked_doctypes,
	search_link_options,
)
from commera.api.admin.settings import coerce_field_value
from commera.shipping.doctype.shipping_service.shipping_service import create_shipping_services
from commera.shipping.providers import (
	get_provider,
	get_provider_class,
	get_provider_doctypes,
	resolve_provider,
)

SERVICE_DOCTYPE = "Shipping Service"
PROFILE_DOCTYPE = "Shipping Provider Profile"

# The optional ShippingProviderBase capability that backs the "Import from Carrier" flow.
SERVICE_CHOICES_CAPABILITY = "service_choices"

LINK_OPTIONS_PATH = "delivery_options.get_link_options"

OPTION_FIELDS = (
	"name",
	"title",
	"description",
	"enabled",
	"provider",
	"service_code",
	"carrier",
	"markup_percent",
	"handling_fee",
	"backup_charge",
)


def build_options() -> list[dict]:
	"""Every delivery option the store has: the ones checkout offers first, each group by title."""
	return frappe.get_all(SERVICE_DOCTYPE, fields=list(OPTION_FIELDS), order_by="enabled desc, title asc")


def build_editor_field_groups() -> list[dict]:
	"""The editor layout, straight off the doctype's own meta. Built against a blank document because one
	layout serves every option - only the labels, fieldtypes, link options and required flags matter."""
	return build_field_groups(SERVICE_DOCTYPE, frappe.new_doc(SERVICE_DOCTYPE))


def build_import_providers() -> list[dict]:
	"""The enabled carriers that can list what their account actually sells.
	A provider that books but publishes no catalogue - Shiprocket picks the courier itself - is left out."""
	registered = set(get_provider_doctypes())
	providers = []
	for profile in frappe.get_all(
		PROFILE_DOCTYPE, filters={"enabled": 1}, fields=["name", "provider_settings"], order_by="name asc"
	):
		if profile.provider_settings not in registered:
			continue
		# The class, not the settings Single: asking the class costs no query per carrier.
		if not get_provider_class(profile.provider_settings).supports(SERVICE_CHOICES_CAPABILITY):
			continue

		providers.append({"provider": profile.name, "label": profile.name})

	return providers


def build_screen() -> dict:
	"""Everything the Delivery Options screen renders, in one read."""
	frappe.has_permission(SERVICE_DOCTYPE, ptype="read", throw=True)

	return {
		"options": build_options(),
		"field_groups": build_editor_field_groups(),
		"import_providers": build_import_providers(),
		# Named rather than assumed by the screen: a picker pointed at a method that does not exist
		# fails the moment the form opens, where a plain box would at least take a typed name.
		"link_options_path": LINK_OPTIONS_PATH,
	}


def get_editable_docfield_map() -> dict:
	"""The docfields this screen renders, keyed by fieldname — the only ones a save may write."""
	return {
		docfield.fieldname: docfield for _group_label, docfield in get_editable_docfields(SERVICE_DOCTYPE)
	}


def resolve_enabled_provider(provider: str) -> str:
	"""The enabled Shipping Provider Profile a request names, refusing one the screen never offered."""
	profile = resolve_provider(provider)
	if not profile:
		frappe.throw(frappe._("Shipping provider {0} is not enabled").format(cstr(provider)))
	return profile


def get_service_choices_controller(provider: str):
	"""The settings Single behind an enabled profile, refusing anything the screen did not offer."""
	profile = resolve_enabled_provider(provider)
	controller = get_provider(profile)
	if not controller.supports(SERVICE_CHOICES_CAPABILITY):
		frappe.throw(frappe._("{0} cannot list its carrier services").format(frappe.bold(profile)))

	return controller


@frappe.whitelist()
def get_delivery_options() -> dict:
	"""The delivery options, the editor layout they share, and the carriers that can be imported from."""
	frappe.only_for("System Manager")

	return build_screen()


@frappe.whitelist(methods=["POST"])
def save_delivery_option(name: str | None = None, values: dict | str | None = None) -> dict:
	"""Create a delivery option, or edit one; a blank `name` creates. Returns the refreshed screen.
	The title is fixed on edit: Sales Order.custom_delivery_option stores the title string, not a link."""
	frappe.only_for("System Manager")
	frappe.has_permission(SERVICE_DOCTYPE, ptype="write", throw=True)

	values = frappe.parse_json(values) if values else {}
	docfield_by_fieldname = get_editable_docfield_map()

	unknown_fieldnames = set(values) - set(docfield_by_fieldname)
	if unknown_fieldnames:
		frappe.throw(
			frappe._("{0} has no field {1}").format(SERVICE_DOCTYPE, ", ".join(sorted(unknown_fieldnames)))
		)

	if name:
		option = frappe.get_doc(SERVICE_DOCTYPE, cstr(name))
		if "title" in values and cstr(values["title"]) != option.title:
			frappe.throw(
				frappe._(
					"{0} cannot be renamed — its name is stored on every order already placed with it. "
					"Create a new delivery option instead."
				).format(frappe.bold(option.title))
			)
	else:
		option = frappe.new_doc(SERVICE_DOCTYPE)

	for fieldname, value in values.items():
		option.set(fieldname, coerce_field_value(docfield_by_fieldname[fieldname].fieldtype, value))

	if not option.provider:
		option.service_code = None
		option.carrier = None

	option.save()
	return build_screen()


@frappe.whitelist(methods=["POST"])
def toggle_delivery_option(name: str, enabled: int | str) -> dict:
	"""Offer a delivery option at checkout, or stop offering it. Returns the refreshed screen."""
	frappe.only_for("System Manager")
	frappe.has_permission(SERVICE_DOCTYPE, ptype="write", throw=True)

	# Saved as a Document, never db_set: on_update is what clears the cached list checkout quotes from,
	# and a disabled option keeps being offered without it.
	option = frappe.get_doc(SERVICE_DOCTYPE, cstr(name))
	option.enabled = cint(enabled)
	option.save()

	return build_screen()


@frappe.whitelist(methods=["POST"])
def delete_delivery_option(name: str) -> dict:
	"""Remove a delivery option. Returns the refreshed screen."""
	frappe.only_for("System Manager")

	frappe.delete_doc(SERVICE_DOCTYPE, cstr(name))
	return build_screen()


@frappe.whitelist()
def get_carrier_service_choices(provider: str) -> dict:
	"""What one carrier account can actually sell, ready to be picked from and imported."""
	frappe.only_for("System Manager")

	return get_service_choices_controller(provider).get_service_choices()


@frappe.whitelist(methods=["POST"])
def import_carrier_services(provider: str, selections: list | str, default_rate: float | str = 0) -> dict:
	"""Turn the picked carrier services into delivery options. Returns the refreshed screen.
	`default_rate` seeds each option's Backup Charge - used when no Shipping Rule band or live quote covers it."""
	frappe.only_for("System Manager")

	# Skips a service_code already imported for this profile, so re-importing after adding a carrier
	# adds only what is new.
	create_shipping_services(resolve_enabled_provider(provider), selections, default_rate)
	return build_screen()


@frappe.whitelist()
def get_link_options(doctype: str, search_text: str | None = None):
	"""Options for a Link control on the delivery-option form. Scoped to what a Shipping Service links to -
	its provider profile - so the picker cannot be turned on an unrelated doctype."""
	frappe.only_for("System Manager")

	if doctype not in get_linked_doctypes(SERVICE_DOCTYPE):
		frappe.throw(frappe._("A delivery option cannot link to {0}.").format(doctype))

	return search_link_options(doctype, search_text)
