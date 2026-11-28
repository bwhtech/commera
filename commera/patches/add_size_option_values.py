import frappe
from frappe.utils import now
from pypika.terms import ExistsCriterion

from commera.api.admin.catalog import DEFAULT_SIZE_VALUE, SIZE_ATTRIBUTE, ensure_attribute_exists
from commera.product_options import OPTION_VALUES_FIELD, VARIANT_OPTION_VALUE

FIELDS = [
	"name",
	"creation",
	"modified",
	"owner",
	"modified_by",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
	"item_code",
	"attribute",
	"value",
	"position",
]


def execute():
	rows = get_sizes_without_option_values()
	if not rows:
		return

	ensure_attribute_exists(SIZE_ATTRIBUTE, DEFAULT_SIZE_VALUE, "OS")
	timestamp = now()
	frappe.db.bulk_insert(
		VARIANT_OPTION_VALUE,
		fields=FIELDS,
		values=[
			(
				frappe.generate_hash(length=10),
				timestamp,
				timestamp,
				"Administrator",
				"Administrator",
				row.idx,
				row.parent,
				OPTION_VALUES_FIELD,
				"Style Attribute Variant",
				row.item_code,
				SIZE_ATTRIBUTE,
				row.size,
				2,
			)
			for row in rows
		],
	)


def get_sizes_without_option_values():
	size_row = frappe.qb.DocType("Color Size Item")
	option_row = frappe.qb.DocType(VARIANT_OPTION_VALUE)
	has_option_row = (
		frappe.qb.from_(option_row)
		.select(option_row.name)
		.where(
			(option_row.parent == size_row.parent)
			& (option_row.item_code == size_row.item_code)
			& (option_row.attribute == SIZE_ATTRIBUTE)
		)
	)
	return (
		frappe.qb.from_(size_row)
		.select(size_row.parent, size_row.item_code, size_row.size, size_row.idx)
		.where(size_row.parenttype == "Style Attribute Variant")
		.where(size_row.size.notnull() & (size_row.size != ""))
		.where(ExistsCriterion(has_option_row).negate())
	).run(as_dict=True)
