# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.utils.data import cstr

from commera.api.admin.catalog import get_value_usage_counts, make_unique_abbreviation
from commera.data.store_options import CATEGORY_OPTIONS, EVERY_STORE_OPTIONS
from commera.swatches import ensure_default_swatch

SETTINGS_DOCTYPE = "Commera Settings"


def get_store_options(category: str | None) -> dict[str, list[str]]:
	options = {attribute: list(values) for attribute, values in EVERY_STORE_OPTIONS.items()}
	for attribute, values in CATEGORY_OPTIONS.get(cstr(category).strip(), {}).items():
		options.setdefault(attribute, []).extend(values)
	return options


def add_store_options(category: str | None = None):
	if category is None:
		category = frappe.db.get_single_value(SETTINGS_DOCTYPE, "store_category")
	options = get_store_options(category)

	attributes = frappe.get_all(
		"Item Attribute", filters={"name": ["in", list(options)]}, fields=["name", "numeric_values"]
	)
	attribute_by_key = {attribute.name.casefold(): attribute for attribute in attributes}
	value_rows = frappe.get_all(
		"Item Attribute Value",
		filters={
			"parent": ["in", [attribute.name for attribute in attributes]],
			"parenttype": "Item Attribute",
		},
		fields=["parent", "attribute_value"],
	)
	values_by_attribute = {}
	for row in value_rows:
		values_by_attribute.setdefault(row.parent, set()).add(cstr(row.attribute_value).casefold())
	used_by_value = get_value_usage_counts([attribute.name for attribute in attributes])

	for attribute_name, values in options.items():
		attribute = attribute_by_key.get(attribute_name.casefold())
		if attribute and attribute.numeric_values:
			continue
		existing_values = values_by_attribute.get(attribute.name, set()) if attribute else set()
		missing_values = [value for value in values if value.casefold() not in existing_values]
		if not missing_values:
			continue

		if attribute:
			attribute_doc = frappe.get_doc("Item Attribute", attribute.name)
		else:
			attribute_doc = frappe.new_doc("Item Attribute")
			attribute_doc.attribute_name = attribute_name
		used_values = {value for parent, value in used_by_value if parent == attribute_doc.name}
		append_attribute_values(attribute_doc, missing_values, used_values)
		attribute_doc.save(ignore_permissions=True)

		for value in missing_values:
			ensure_default_swatch(attribute_doc.name, value)


def append_attribute_values(attribute_doc, values: list[str], used_values: set[str]):
	holder_by_abbreviation = {cstr(row.abbr).casefold(): row for row in attribute_doc.item_attribute_values}
	for value in values:
		abbreviation = get_value_abbreviation(value)
		holder = holder_by_abbreviation.get(abbreviation.casefold())
		if holder and holder.attribute_value not in used_values:
			holder.abbr = make_unique_abbreviation(
				holder.attribute_value,
				set(holder_by_abbreviation),
				get_value_abbreviation(holder.attribute_value),
			)
			holder_by_abbreviation[holder.abbr.casefold()] = holder
		elif holder:
			abbreviation = make_unique_abbreviation(value, set(holder_by_abbreviation), abbreviation)

		row = attribute_doc.append("item_attribute_values", {"attribute_value": value, "abbr": abbreviation})
		holder_by_abbreviation[abbreviation.casefold()] = row


def get_value_abbreviation(value: str) -> str:
	return cstr(value).replace(" ", "").upper()
