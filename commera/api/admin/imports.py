# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""Bulk product import: a spreadsheet template, and the importer that reads one back. One row is one
colour/size; rows sharing a Product Title become one product, priced once, via catalog.create_product."""

import os
import re

import frappe
from frappe import _
from frappe.utils import create_batch
from frappe.utils.csvutils import read_csv_content
from frappe.utils.data import cint, cstr, flt
from frappe.utils.xlsxutils import build_xlsx_response, read_xlsx_file_from_attached_file

from commera.api.admin.catalog import create_product
from commera.telemetry import configuration, data_source
from commera.utils import IN_CLAUSE_CHUNK_SIZE

TEMPLATE_HEADERS = [
	"Product Title",
	"Collection",
	"Color",
	"Size",
	"Compare at price",
	"Selling price",
	"Stock",
]

# Every field an importer accepts, in TEMPLATE_HEADERS order, with the synonyms an uploaded file's
# own header row is matched against (case/space/punctuation-insensitive) — see suggest_mapping().
FIELD_SYNONYMS = {
	"title": ["product title", "title", "product name", "name"],
	"collection": ["collection", "category", "item group"],
	"color": ["color", "colour"],
	"size": ["size"],
	"compare_at_price": ["compare at price", "mrp", "compare at", "list price"],
	"sale_price": ["selling price", "price", "sale price"],
	"stock": ["stock", "quantity", "qty", "stock quantity", "qty on hand"],
}
FIELD_LABELS = dict(zip(FIELD_SYNONYMS, TEMPLATE_HEADERS, strict=True))
REQUIRED_FIELDS = ["title", "collection", "color", "size"]

# Every product this importer creates uses this store's own Color/Size attributes — the same two
# create_product's own Trap 2 guard requires (generate_variants() depends on the exact name "Size").
OPTION_ATTRIBUTE = "Color"
SIZE_ATTRIBUTE = "Size"


def normalize_header(text):
	return "".join(ch for ch in cstr(text).strip().casefold() if ch.isalnum() or ch == " ").strip()


@frappe.whitelist()
def download_product_template():
	"""A ready-to-fill spreadsheet whose header row matches parse_and_validate() column for column."""
	frappe.has_permission("Item", ptype="create", throw=True)

	example_collection = frappe.db.get_value("Item Group", {"is_group": 0}) or "Apparel"
	example_rows = [
		["Cotton Oversized Tee", example_collection, "Black", "M", 1299, 999, 24],
		["Cotton Oversized Tee", example_collection, "Black", "L", 1299, 999, 18],
		["Cotton Oversized Tee", example_collection, "Sand", "M", 1299, 999, 12],
	]
	build_xlsx_response([TEMPLATE_HEADERS, *example_rows], "Product import template")


def read_uploaded_rows(file_url):
	"""The file's raw grid, header row included, blank rows dropped."""
	file_doc = frappe.get_doc("File", {"file_url": file_url})
	if cstr(file_doc.file_name).lower().endswith(".csv"):
		rows = read_csv_content(file_doc.get_content())
	else:
		rows = read_xlsx_file_from_attached_file(file_url=file_url)
	return [row for row in rows if any(cstr(cell).strip() for cell in row)]


def suggest_mapping(headers):
	"""Best-guess header -> field, so a file built from download_product_template() maps itself."""
	mapping = {}
	confidence = {}
	for header in headers:
		normalized = normalize_header(header)
		field, level = "", "none"
		for candidate, synonyms in FIELD_SYNONYMS.items():
			if normalized == synonyms[0]:
				field, level = candidate, "high"
				break
			if normalized in synonyms:
				field, level = candidate, "medium"
				break
		mapping[header] = field
		confidence[header] = level
	return mapping, confidence


def parse_and_validate(file_url: str, column_mapping: dict | None = None):
	"""One dry-run pass over the file: every row comes back with its own issue, or none. Nothing is
	written here — this is what both the Review step and run_import()'s own safety check share."""
	rows = read_uploaded_rows(file_url)
	if not rows:
		frappe.throw(_("The file has no rows"))

	headers = [cstr(cell) for cell in rows[0]]
	data_rows = rows[1:]

	suggested_mapping, confidence = suggest_mapping(headers)
	mapping = (
		{header: column_mapping.get(header, "") for header in headers}
		if column_mapping
		else suggested_mapping
	)

	missing_required = [FIELD_LABELS[field] for field in REQUIRED_FIELDS if field not in mapping.values()]
	if missing_required:
		frappe.throw(_("These columns are not mapped: {0}").format(", ".join(missing_required)))

	column_index_by_field = {}
	for index, header in enumerate(headers):
		field = mapping.get(header)
		if field:
			column_index_by_field.setdefault(field, index)

	def cell(row, field):
		index = column_index_by_field.get(field)
		return row[index] if index is not None and index < len(row) else None

	def as_amount(raw, label, issue_holder):
		# flt() swallows a bad string down to 0.0 instead of raising, which would silently turn
		# "not-a-number" into an unpriced row — parse strictly here so that surfaces as an error.
		if raw in (None, ""):
			return 0
		try:
			return flt(float(cstr(raw).replace(",", "").strip()))
		except (TypeError, ValueError):
			issue_holder.setdefault("issue", {"level": "error", "text": f'{label} "{raw}" is not a number'})
			return 0

	parsed_rows = []
	seen_variants = {}
	product_first_row = {}
	for offset, row in enumerate(data_rows):
		row_number = offset + 2  # +1 for the header row, +1 for 1-indexed row numbers
		title = cstr(cell(row, "title")).strip()
		collection = cstr(cell(row, "collection")).strip()
		color = cstr(cell(row, "color")).strip()
		size = cstr(cell(row, "size")).strip()

		holder = {}
		compare_at_price = as_amount(cell(row, "compare_at_price"), "Compare at price", holder)
		sale_price = as_amount(cell(row, "sale_price"), "Selling price", holder)
		stock = as_amount(cell(row, "stock"), "Stock", holder)
		issue = holder.get("issue")

		if not issue and not title:
			issue = {"level": "error", "text": "Product title is missing"}
		if not issue and not collection:
			issue = {"level": "error", "text": "Collection is missing"}
		elif not issue and not frappe.db.exists("Item Group", collection):
			issue = {"level": "error", "text": f'Collection "{collection}" does not exist — create it first'}
		if not issue and not color:
			issue = {"level": "error", "text": "Color is missing"}
		if not issue and not size:
			issue = {"level": "error", "text": "Size is missing"}

		if not issue and title:
			variant_key = (title.casefold(), color.casefold(), size.casefold())
			if variant_key in seen_variants:
				issue = {
					"level": "error",
					"text": f"Duplicate of row {seen_variants[variant_key]} (same title, colour and size)",
				}
			else:
				seen_variants[variant_key] = row_number

		if not issue and title:
			first = product_first_row.get(title.casefold())
			if first is None:
				product_first_row[title.casefold()] = {
					"row": row_number,
					"collection": collection,
					"compare_at_price": compare_at_price,
					"sale_price": sale_price,
				}
			elif collection and collection != first["collection"]:
				issue = {
					"level": "error",
					"text": f'Collection does not match row {first["row"]} for "{title}" ({first["collection"]})',
				}
			elif compare_at_price != first["compare_at_price"] or sale_price != first["sale_price"]:
				issue = {
					"level": "error",
					"text": (
						f'Price does not match row {first["row"]} for "{title}" — '
						"one price applies to the whole product"
					),
				}

		if not issue and not compare_at_price and not sale_price:
			issue = {"level": "warning", "text": "No price set — product is created without a price"}

		parsed_rows.append(
			{
				"row": row_number,
				"title": title,
				"collection": collection,
				"color": color,
				"size": size,
				"compare_at_price": compare_at_price,
				"sale_price": sale_price,
				"stock": stock,
				"issue": issue,
			}
		)

	groups = group_valid_rows(parsed_rows)
	counts = {
		"total": len(parsed_rows),
		"errors": sum(1 for row in parsed_rows if row["issue"] and row["issue"]["level"] == "error"),
		"warnings": sum(1 for row in parsed_rows if row["issue"] and row["issue"]["level"] == "warning"),
		"ready": sum(1 for row in parsed_rows if not row["issue"] or row["issue"]["level"] == "warning"),
		"products": len(groups),
	}

	return {
		"headers": headers,
		"mapping": mapping,
		"confidence": confidence,
		"rows": parsed_rows,
		"counts": counts,
	}


def group_valid_rows(parsed_rows):
	"""One entry per product title with zero error rows — only these are ever written. A title
	whose every row errors, or whose only clean rows are duplicates of an error, never groups."""
	groups = {}
	order = []
	for row in parsed_rows:
		if row["issue"] and row["issue"]["level"] == "error":
			continue
		key = row["title"].casefold()
		if key not in groups:
			groups[key] = {
				"title": row["title"],
				"collection": row["collection"],
				"compare_at_price": row["compare_at_price"],
				"sale_price": row["sale_price"],
				"rows": [],
			}
			order.append(key)
		groups[key]["rows"].append(row)
	return [groups[key] for key in order]


def group_to_option_sizes(rows):
	option_sizes = {}
	for row in rows:
		option_sizes.setdefault(row["color"], []).append(row["size"])
	return [{"option": option, "sizes": sizes} for option, sizes in option_sizes.items()]


def slugify(text):
	"""Lowercase, with every run of non-alphanumeric characters collapsed to a single dash — the one
	spelling both a product's title/colour and a photo's file name are reduced to before comparing."""
	return re.sub(r"[^a-z0-9]+", "-", cstr(text).casefold()).strip("-")


def get_image_group_key(title, color):
	"""Photos hang off the colour-level Style Attribute Variant, not off a size, so the unit a photo
	belongs to is one colour of one product group — group_valid_rows' own key plus the colour."""
	return f"{cstr(title).casefold()}::{cstr(color).casefold()}"


def get_image_groups(parsed_rows):
	"""One entry per colour of every product group that validated clean — what a photo can land on."""
	groups = {}
	for group in group_valid_rows(parsed_rows):
		for row in group["rows"]:
			key = get_image_group_key(group["title"], row["color"])
			if key not in groups:
				groups[key] = {
					"key": key,
					"title": group["title"],
					"color": row["color"],
					"slug": f"{slugify(group['title'])}-{slugify(row['color'])}",
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
			_("These images are not on the server any more — upload them again: {0}").format(
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


@frappe.whitelist(methods=["POST"])
def match_import_images(
	file_url: str, column_mapping: dict | str | None = None, image_files: list | str | None = None
):
	"""Which uploaded photo belongs to which product colour, by file name. Nothing is written."""
	frappe.has_permission("Item", ptype="create", throw=True)
	if isinstance(column_mapping, str):
		column_mapping = frappe.parse_json(column_mapping)

	uploaded_files = read_uploaded_image_files(image_files)
	result = parse_and_validate(file_url, column_mapping)
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


def attach_group_images(item_template, group, file_urls_by_key):
	"""Hand one product's photos to the colour-level variants they were assigned to, and say how many
	landed. Every write goes through Style Attribute Variant.add_images, which owns the child rows."""
	file_urls_by_color = {}
	for row in group["rows"]:
		key = get_image_group_key(group["title"], row["color"])
		# Keyed casefolded, exactly as the group key is: a CSV mixing "Black" and "black" describes
		# one colour and one variant, and two entries here would attach its photos twice.
		color = cstr(row["color"]).casefold()
		if file_urls_by_key.get(key) and color not in file_urls_by_color:
			file_urls_by_color[color] = file_urls_by_key[key]
	if not file_urls_by_color:
		return 0

	configurator = frappe.db.get_value("Style Attribute Configurator", {"item_template": item_template})
	variants = frappe.get_all(
		"Style Attribute Variant", filters={"configurator": configurator}, fields=["name", "attribute_value"]
	)
	variant_by_option = {cstr(variant.attribute_value).casefold(): variant.name for variant in variants}

	attached = 0
	for color, file_urls in file_urls_by_color.items():
		variant_name = variant_by_option.get(color)
		if not variant_name:
			frappe.throw(_("{0} has no {1} to put photos on").format(group["title"], color))
		# ponytail: one get_doc per colour because add_images validates and saves the variant,
		# revisit if a single import ever carries more colours than a page of variants.
		frappe.get_doc("Style Attribute Variant", variant_name).add_images(file_urls)
		attached += len(file_urls)
	return attached


def receive_group_stock(item_template, rows):
	"""Opening stock for a just-created product, one grouped read plus one receipt per colour —
	not one query per row regardless of how many size rows the file had for this product."""
	rows_with_stock = [row for row in rows if flt(row["stock"]) > 0]
	if not rows_with_stock:
		return

	configurator = frappe.db.get_value("Style Attribute Configurator", {"item_template": item_template})
	variants = frappe.get_all(
		"Style Attribute Variant", filters={"configurator": configurator}, fields=["name", "attribute_value"]
	)
	variant_by_option = {cstr(variant.attribute_value).casefold(): variant.name for variant in variants}

	size_items = frappe.get_all(
		"Color Size Item",
		filters={
			"parent": ["in", [variant.name for variant in variants]],
			"parenttype": "Style Attribute Variant",
		},
		fields=["parent", "size", "item_code"],
	)
	item_code_by_variant_size = {(row.parent, cstr(row.size).casefold()): row.item_code for row in size_items}

	quantities_by_variant = {}
	for row in rows_with_stock:
		variant_name = variant_by_option.get(row["color"].casefold())
		item_code = variant_name and item_code_by_variant_size.get((variant_name, row["size"].casefold()))
		if item_code:
			quantities_by_variant.setdefault(variant_name, {})[item_code] = flt(row["stock"])

	for variant_name, quantities in quantities_by_variant.items():
		frappe.get_doc("Style Attribute Variant", variant_name).receive_stock(quantities)


@frappe.whitelist()
def validate_import(file_url: str, column_mapping: dict | str | None = None):
	"""The Review step's data — a dry run, nothing written."""
	frappe.has_permission("Item", ptype="create", throw=True)
	if isinstance(column_mapping, str):
		column_mapping = frappe.parse_json(column_mapping)
	return parse_and_validate(file_url, column_mapping)


@frappe.whitelist(methods=["POST"])
@data_source("import")
def run_import(
	file_url: str, column_mapping: dict | str | None = None, image_assignments: dict | str | None = None
):
	"""Commits every product group that validated clean. A group that fails while being created is rolled
	back to its own savepoint, and photos are attached after their product exists, inside their own one."""
	frappe.has_permission("Item", ptype="create", throw=True)
	if isinstance(column_mapping, str):
		column_mapping = frappe.parse_json(column_mapping)
	file_urls_by_key = read_image_assignments(image_assignments)

	if not frappe.db.exists("Item Attribute", OPTION_ATTRIBUTE):
		frappe.throw(
			_('This store has no Item Attribute named "{0}" — create it first.').format(OPTION_ATTRIBUTE)
		)
	if not frappe.db.exists("Item Attribute", SIZE_ATTRIBUTE):
		frappe.throw(
			_('This store has no Item Attribute named "{0}" — create it first.').format(SIZE_ATTRIBUTE)
		)

	result = parse_and_validate(file_url, column_mapping)
	groups = group_valid_rows(result["rows"])

	created = []
	creation_errors = []
	image_errors = []
	images_attached = 0
	used_image_keys = set()
	for group in groups:
		# MariaDB refuses "rollback to savepoint 6e2e6705d9" — a savepoint is an identifier, and a
		# generated hash starts with a digit often enough, so every name here is given a letter first.
		savepoint = f"product_{frappe.generate_hash(length=10)}"
		try:
			frappe.db.savepoint(savepoint)
			created_product = create_product(
				title=group["title"],
				collection=group["collection"],
				option_attribute=OPTION_ATTRIBUTE,
				size_attribute=SIZE_ATTRIBUTE,
				option_sizes=group_to_option_sizes(group["rows"]),
				price=group["compare_at_price"] or None,
				sale_price=group["sale_price"] or None,
			)
			receive_group_stock(created_product["name"], group["rows"])
		except Exception as error:
			frappe.db.rollback(save_point=savepoint)
			message = str(error)
			for row in group["rows"]:
				creation_errors.append({"row": row["row"], "message": message})
		else:
			created.append({"item_template": created_product["name"], "title": group["title"]})
			used_image_keys.update(get_image_group_key(group["title"], row["color"]) for row in group["rows"])
			image_savepoint = f"images_{frappe.generate_hash(length=10)}"
			try:
				frappe.db.savepoint(image_savepoint)
				images_attached += attach_group_images(created_product["name"], group, file_urls_by_key)
			except Exception as error:
				frappe.db.rollback(save_point=image_savepoint)
				message = str(error)
				for row in group["rows"]:
					image_errors.append({"row": row["row"], "message": message})

	row_number_by_key = {}
	for row in result["rows"]:
		row_number_by_key.setdefault(get_image_group_key(row["title"], row["color"]), row["row"])

	for key, file_urls in file_urls_by_key.items():
		if key in used_image_keys or not file_urls:
			continue
		image_errors.append(
			{
				"row": row_number_by_key.get(key),
				"message": _("No product was created for {0}, so its {1} photos were not attached").format(
					key, len(file_urls)
				),
			}
		)

	# Rows that never made it into a group at all kept their own validation message from the dry run.
	validation_errors = [
		{"row": row["row"], "message": row["issue"]["text"]}
		for row in result["rows"]
		if row["issue"] and row["issue"]["level"] == "error"
	]

	configuration.products_imported(
		len(result["rows"]), len(created), len(validation_errors) + len(creation_errors)
	)
	return {
		"created": created,
		"created_count": len(created),
		"row_errors": validation_errors + creation_errors,
		"counts": result["counts"],
		"images_attached": images_attached,
		"image_errors": image_errors,
	}
