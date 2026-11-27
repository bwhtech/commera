# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""Bulk product import: a spreadsheet template, and the importer that reads one back. One row is one
colour/size; rows sharing a Product Title become one product, priced once, via catalog.create_product."""

import os
import re

import frappe
from frappe import _
from frappe.utils import create_batch
from frappe.utils.data import cint, cstr, flt
from frappe.utils.xlsxutils import build_xlsx_response

from commera.api.admin.catalog import (
	DEFAULT_OPTION_VALUE,
	DEFAULT_SIZE_VALUE,
	create_product,
	get_collections,
)
from commera.api.admin.import_rows import (
	FIELD_LABELS,
	TEMPLATE_HEADERS,
	get_image_group_key,
	group_valid_rows,
	parse_and_validate,
)
from commera.commera_ecommerce.doctype.bulk_publish_variants.bulk_publish_variants import publish_variants
from commera.commera_ecommerce.doctype.commera_settings.editor_input import parse_list
from commera.utils import IN_CLAUSE_CHUNK_SIZE

# Products with a color use this store's own Color attribute.
OPTION_ATTRIBUTE = "Color"


@frappe.whitelist()
def download_product_template():
	"""A ready-to-fill spreadsheet whose header row matches parse_and_validate() column for column. The
	mug row shows that color and size are optional."""
	frappe.has_permission("Item", ptype="create", throw=True)

	collections = get_collections()
	example_collection = collections[0] if collections else ""
	example_rows = [
		["Cotton Oversized Tee", example_collection, "Black", "M", 999, 1299, 24],
		["Cotton Oversized Tee", example_collection, "Black", "L", 999, 1299, 18],
		["Cotton Oversized Tee", example_collection, "Sand", "M", 999, 1299, 12],
		["Ceramic Mug", example_collection, "", "", 450, "", 10],
	]
	build_xlsx_response([TEMPLATE_HEADERS, *example_rows], "Product import template")


def get_product_options(rows):
	"""What create_product needs for one product: (option attribute, option_sizes)."""
	if any(row["color"] for row in rows):
		sizes_by_color = {}
		for row in rows:
			sizes = sizes_by_color.setdefault(row["color"], [])
			if row["size"]:
				sizes.append(row["size"])
		return OPTION_ATTRIBUTE, [
			{"option": color, "sizes": sizes} for color, sizes in sizes_by_color.items()
		]
	sizes = [row["size"] for row in rows if row["size"]]
	if not sizes:
		return None, []
	# No attribute: create_product hangs sizes alone on its own hidden option, as it does for no options.
	return None, [{"option": DEFAULT_OPTION_VALUE, "sizes": sizes}]


def get_variant_option(row):
	"""The option value a row's variant carries, casefolded as Style Attribute Variant lookups are."""
	return cstr(row["color"] or DEFAULT_OPTION_VALUE).casefold()


def get_variant_size(row):
	return cstr(row["size"] or DEFAULT_SIZE_VALUE).casefold()


def slugify(text):
	"""Lowercase, with every run of non-alphanumeric characters collapsed to a single dash — the one
	spelling both a product's title/colour and a photo's file name are reduced to before comparing."""
	return re.sub(r"[^a-z0-9]+", "-", cstr(text).casefold()).strip("-")


def get_image_groups(parsed_rows):
	"""One entry per color of every product group that validated clean, which is what a photo can land on.
	A product without colors is one group, named by its title alone."""
	groups = {}
	for group in group_valid_rows(parsed_rows):
		for row in group["rows"]:
			key = get_image_group_key(group["title"], row["color"])
			if key not in groups:
				groups[key] = {
					"key": key,
					"title": group["title"],
					"color": row["color"],
					"slug": "-".join(filter(None, [slugify(group["title"]), slugify(row["color"])])),
				}
	return list(groups.values())


def match_files_to_groups(groups, uploaded_files):
	"""A file lands on the group whose slug its own name equals or starts with, dash-separated. The longest
	matching slug wins, so "tee-black" never steals a photo belonging to "tee-black-ribbed"."""
	groups_by_slug_length = sorted(groups, key=lambda group: len(group["slug"]), reverse=True)

	matched = []
	unmatched = []
	for uploaded_file in uploaded_files:
		file_slug = slugify(os.path.splitext(uploaded_file["file_name"])[0])
		group = next(
			(
				group
				for group in groups_by_slug_length
				if group["slug"] and (file_slug == group["slug"] or file_slug.startswith(group["slug"] + "-"))
			),
			None,
		)
		if group:
			matched.append(
				{**uploaded_file, "key": group["key"], "title": group["title"], "color": group["color"]}
			)
		else:
			unmatched.append(dict(uploaded_file))
	return matched, unmatched


def validate_image_urls(file_urls, names_by_url: dict | None = None):
	"""Every URL must still resolve to a File, and to a public one - Style Attribute Variant.add_images only
	checks that *some* File row carries the url. Chunked: one IN (...) of every upload falls apart."""
	unique_urls = list(dict.fromkeys(file_urls))
	if not unique_urls:
		return

	files = []
	for url_chunk in create_batch(unique_urls, IN_CLAUSE_CHUNK_SIZE):
		files += frappe.get_all(
			"File", filters={"file_url": ["in", url_chunk]}, fields=["file_url", "is_private"]
		)

	names_by_url = names_by_url or {}
	existing_urls = {row.file_url for row in files}
	private_urls = {row.file_url for row in files if cint(row.is_private)}

	missing = [names_by_url.get(url, url) for url in unique_urls if url not in existing_urls]
	if missing:
		frappe.throw(
			_("These images are not on the server any more. Upload them again: {0}").format(
				", ".join(missing)
			)
		)

	private = [names_by_url.get(url, url) for url in unique_urls if url in private_urls]
	if private:
		frappe.throw(
			_("These images are private and cannot go on a storefront page: {0}").format(", ".join(private))
		)


def read_uploaded_image_files(image_files):
	"""Each uploaded image must still resolve to a File - the same guard Style Attribute Variant.add_images
	enforces, checked here where a merchant can still re-upload."""
	entries = frappe.parse_json(image_files) or []
	if not isinstance(entries, list):
		frappe.throw(_("Images must be sent as a list of file names and file URLs"))

	uploaded_files = []
	for entry in entries:
		if not isinstance(entry, dict):
			frappe.throw(_("Each image must be sent as a file name and a file URL"))
		url = cstr(entry.get("file_url")).strip()
		if not url:
			frappe.throw(_("An image was sent without a file URL"))
		uploaded_files.append(
			{"file_url": url, "file_name": cstr(entry.get("file_name")).strip() or url.rsplit("/", 1)[-1]}
		)

	validate_image_urls(
		[uploaded_file["file_url"] for uploaded_file in uploaded_files],
		{uploaded_file["file_url"]: uploaded_file["file_name"] for uploaded_file in uploaded_files},
	)

	return uploaded_files


def read_column_mapping(column_mapping):
	return frappe.parse_json(column_mapping) if isinstance(column_mapping, str) else column_mapping


def parse_complete_file(file_url, column_mapping, default_collection):
	"""Refuses a file whose required fields are still unmatched: the dashboard cannot leave the Map step
	that way, so reaching here with one missing is a bug, not a merchant mistake."""
	result = parse_and_validate(file_url, column_mapping, default_collection)
	if result["missing"]:
		frappe.throw(
			_("Match a column to {0} first").format(
				", ".join(_(FIELD_LABELS[field]) for field in result["missing"])
			)
		)
	return result


@frappe.whitelist(methods=["POST"])
def match_import_images(
	file_url: str,
	column_mapping: dict | str | None = None,
	image_files: list | str | None = None,
	default_collection: str | None = None,
):
	"""Which uploaded photo belongs to which product color, by file name. Nothing is written."""
	frappe.has_permission("Item", ptype="create", throw=True)
	column_mapping = read_column_mapping(column_mapping)

	uploaded_files = read_uploaded_image_files(image_files)
	result = parse_complete_file(file_url, column_mapping, default_collection)
	groups = get_image_groups(result["rows"])
	matched, unmatched = match_files_to_groups(groups, uploaded_files)

	image_count_by_key = {}
	for match in matched:
		image_count_by_key[match["key"]] = image_count_by_key.get(match["key"], 0) + 1

	groups = [{**group, "image_count": image_count_by_key.get(group["key"], 0)} for group in groups]

	return {
		"matched": matched,
		"unmatched": unmatched,
		"groups": groups,
		"counts": {
			"matched": len(matched),
			"unmatched": len(unmatched),
			"groups": len(groups),
			"groups_without_photo": sum(1 for group in groups if not group["image_count"]),
		},
	}


def read_image_assignments(image_assignments):
	"""{group key: [file_url, ...]} as match_import_images returned it, validated on arrival: a non-dict
	payload would otherwise raise past run_import's per-group savepoints and roll the whole request back."""
	assignments = frappe.parse_json(image_assignments) or {}
	if not isinstance(assignments, dict):
		frappe.throw(_("Image assignments must be sent as a group name against its list of photos"))

	file_urls_by_key = {}
	for key, file_urls in assignments.items():
		if not isinstance(file_urls, list):
			frappe.throw(_("The photos for {0} must be sent as a list of file URLs").format(key))
		urls = [cstr(file_url).strip() for file_url in file_urls]
		if not all(urls):
			frappe.throw(_("A photo assigned to {0} was sent without a file URL").format(key))
		file_urls_by_key[cstr(key)] = urls

	validate_image_urls([url for urls in file_urls_by_key.values() for url in urls])
	return file_urls_by_key


def get_variant_by_option(item_template):
	"""{casefolded option value: Style Attribute Variant name} for a just-created product."""
	configurator = frappe.db.get_value("Style Attribute Configurator", {"item_template": item_template})
	variants = frappe.get_all(
		"Style Attribute Variant", filters={"configurator": configurator}, fields=["name", "attribute_value"]
	)
	return {cstr(variant.attribute_value).casefold(): variant.name for variant in variants}


def attach_group_images(item_template, group, file_urls_by_key):
	"""Hand one product's photos to the color-level variants they were assigned to, and say how many
	landed. Every write goes through Style Attribute Variant.add_images, which owns the child rows."""
	file_urls_by_option = {}
	for row in group["rows"]:
		key = get_image_group_key(group["title"], row["color"])
		# Keyed casefolded, exactly as the group key is: a CSV mixing "Black" and "black" describes
		# one color and one variant, and two entries here would attach its photos twice.
		option = get_variant_option(row)
		if file_urls_by_key.get(key) and option not in file_urls_by_option:
			file_urls_by_option[option] = file_urls_by_key[key]
	if not file_urls_by_option:
		return 0

	variant_by_option = get_variant_by_option(item_template)
	attached = 0
	for option, file_urls in file_urls_by_option.items():
		variant_name = variant_by_option.get(option)
		if not variant_name:
			frappe.throw(_("{0} has no {1} to put photos on").format(group["title"], option))
		# ponytail: one get_doc per color because add_images validates and saves the variant,
		# revisit if a single import ever carries more colors than a page of variants.
		frappe.get_doc("Style Attribute Variant", variant_name).add_images(file_urls)
		attached += len(file_urls)
	return attached


def receive_group_stock(item_template, rows):
	"""Opening stock for a just-created product, one grouped read plus one receipt per color,
	not one query per row regardless of how many size rows the file had for this product."""
	rows_with_stock = [row for row in rows if flt(row["stock"]) > 0]
	if not rows_with_stock:
		return

	variant_by_option = get_variant_by_option(item_template)
	size_items = frappe.get_all(
		"Color Size Item",
		filters={"parent": ["in", list(variant_by_option.values())], "parenttype": "Style Attribute Variant"},
		fields=["parent", "size", "item_code"],
	)
	item_code_by_variant_size = {(row.parent, cstr(row.size).casefold()): row.item_code for row in size_items}

	quantities_by_variant = {}
	for row in rows_with_stock:
		variant_name = variant_by_option.get(get_variant_option(row))
		item_code = variant_name and item_code_by_variant_size.get((variant_name, get_variant_size(row)))
		if item_code:
			quantities_by_variant.setdefault(variant_name, {})[item_code] = flt(row["stock"])

	for variant_name, quantities in quantities_by_variant.items():
		frappe.get_doc("Style Attribute Variant", variant_name).receive_stock(quantities)


def create_group_product(group):
	option_attribute, option_sizes = get_product_options(group["rows"])
	if option_attribute == OPTION_ATTRIBUTE and not frappe.db.exists("Item Attribute", OPTION_ATTRIBUTE):
		frappe.throw(
			_('This store has no Item Attribute named "{0}". Create it first.').format(OPTION_ATTRIBUTE)
		)
	created_product = create_product(
		title=group["title"],
		collection=group["collection"],
		option_attribute=option_attribute,
		option_sizes=option_sizes,
		price=group["compare_at_price"] or group["sale_price"],
		sale_price=group["sale_price"],
	)
	receive_group_stock(created_product["name"], group["rows"])
	return created_product["name"]


def row_messages(rows, message):
	return [{"row": row["row"], "message": message} for row in rows]


def import_group(group, file_urls_by_key, outcome):
	"""Create one product and attach its photos, each inside its own savepoint, so a product that fails
	costs only its own rows and photos that fail cost only the photos."""
	# MariaDB refuses "rollback to savepoint 6e2e6705d9": a savepoint is an identifier, and a
	# generated hash starts with a digit often enough, so every name here is given a letter first.
	savepoint = f"product_{frappe.generate_hash(length=10)}"
	try:
		frappe.db.savepoint(savepoint)
		item_template = create_group_product(group)
	except Exception as creation_error:
		frappe.db.rollback(save_point=savepoint)
		outcome["row_errors"] += row_messages(group["rows"], str(creation_error))
		return

	outcome["created"].append({"item_template": item_template, "title": group["title"]})
	outcome["used_image_keys"].update(
		get_image_group_key(group["title"], row["color"]) for row in group["rows"]
	)
	image_savepoint = f"images_{frappe.generate_hash(length=10)}"
	try:
		frappe.db.savepoint(image_savepoint)
		outcome["images_attached"] += attach_group_images(item_template, group, file_urls_by_key)
	except Exception as image_error:
		frappe.db.rollback(save_point=image_savepoint)
		outcome["image_errors"] += row_messages(group["rows"], str(image_error))


def get_orphan_image_errors(parsed_rows, file_urls_by_key, used_image_keys):
	"""Photos assigned to a product that was never created, named by the row they came from."""
	first_row_by_key = {}
	for row in parsed_rows:
		first_row_by_key.setdefault(row["image_key"], row)
	errors = []
	for key, file_urls in file_urls_by_key.items():
		if key in used_image_keys or not file_urls:
			continue
		row = first_row_by_key.get(key, {})
		name = " · ".join(filter(None, [row.get("title"), row.get("color")])) or key
		errors.append(
			{
				"row": row.get("row"),
				"message": _("No product was created for {0}, so its {1} photos were not attached").format(
					name, len(file_urls)
				),
			}
		)
	return errors


@frappe.whitelist()
def validate_import(
	file_url: str, column_mapping: dict | str | None = None, default_collection: str | None = None
):
	"""The Map and Review steps' data: a dry run, nothing written."""
	frappe.has_permission("Item", ptype="create", throw=True)
	column_mapping = read_column_mapping(column_mapping)
	return parse_and_validate(file_url, column_mapping, default_collection)


@frappe.whitelist(methods=["POST"])
def run_import(
	file_url: str,
	column_mapping: dict | str | None = None,
	image_assignments: dict | str | None = None,
	default_collection: str | None = None,
):
	"""Commits every product group that validated clean, as drafts. Publishing is the merchant's next
	step (publish_imported_products)."""
	frappe.has_permission("Item", ptype="create", throw=True)
	column_mapping = read_column_mapping(column_mapping)
	file_urls_by_key = read_image_assignments(image_assignments)
	result = parse_complete_file(file_url, column_mapping, default_collection)

	outcome = {
		"created": [],
		"row_errors": [],
		"image_errors": [],
		"images_attached": 0,
		"used_image_keys": set(),
	}
	for group in group_valid_rows(result["rows"]):
		import_group(group, file_urls_by_key, outcome)

	# Rows that never made it into a group at all kept their own validation message from the dry run.
	validation_errors = [
		{"row": row["row"], "message": row["issue"]["text"]}
		for row in result["rows"]
		if row["issue"] and row["issue"]["level"] == "error"
	]
	orphan_errors = get_orphan_image_errors(result["rows"], file_urls_by_key, outcome["used_image_keys"])

	return {
		"created": outcome["created"],
		"created_count": len(outcome["created"]),
		"row_errors": validation_errors + outcome["row_errors"],
		"counts": result["counts"],
		"images_attached": outcome["images_attached"],
		"image_errors": outcome["image_errors"] + orphan_errors,
	}


@frappe.whitelist(methods=["POST"])
def publish_imported_products(item_templates: list | str):
	"""Publish every draft color of the products one import created: the Done step's Publish all."""
	frappe.has_permission("Style Attribute Variant", ptype="write", throw=True)
	item_templates = parse_list(item_templates)
	drafts = []
	for chunk in create_batch(item_templates, IN_CLAUSE_CHUNK_SIZE):
		drafts += frappe.get_all(
			"Style Attribute Variant",
			filters={"item_style": ["in", chunk], "is_published": 0},
			fields=["name", "item_style"],
		)
	published = set(publish_variants(1, names=[draft.name for draft in drafts])) if drafts else set()
	not_published = {draft.item_style for draft in drafts if draft.name not in published}
	return {
		"published": len({draft.item_style for draft in drafts} - not_published),
		"not_published": sorted(not_published),
	}
