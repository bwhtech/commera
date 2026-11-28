"""Turn existing ERPNext Items into draft Commera products. The Items, their prices and their stock stay
as they are: only a Style Attribute Configurator, its options and their size rows are added around them."""

import hashlib

import frappe
from frappe import _
from frappe.utils import create_batch, now
from frappe.utils.background_jobs import get_job_status, is_job_enqueued
from frappe.utils.data import cstr
from rq.job import JobStatus

from commera.api.admin.catalog import (
	DEFAULT_OPTION_ATTRIBUTE,
	DEFAULT_OPTION_VALUE,
	DEFAULT_SIZE_VALUE,
	SIZE_ATTRIBUTE,
	ensure_attribute_exists,
	get_ecommerce_stock,
	get_selling_rates,
)
from commera.api.admin.imports import publish_drafts
from commera.commera_ecommerce.doctype.commera_settings.commera_settings import create_configurator_log
from commera.product_collections import COLLECTIONS_FIELD, PRODUCT_COLLECTION
from commera.swatches import COLOUR_ATTRIBUTE, DUPLICATE_COLOUR_ATTRIBUTE
from commera.utils import IN_CLAUSE_CHUNK_SIZE
from commera.webshop_migration import apply_webshop_extras

JOB_ID = "commera-erpnext-import"
JOB_TIMEOUT = 2 * 60 * 60
STATUS_SECONDS = 24 * 60 * 60
BATCH_SIZE = 50
LOG_DOCTYPE = "Bulk Style Attribute Configurator Creation Log"
PRODUCT_DOCTYPE = "Style Attribute Variant"
COLOUR_ATTRIBUTES = (COLOUR_ATTRIBUTE, DUPLICATE_COLOUR_ATTRIBUTE)
REQUIRED_SETTINGS = ("company", "default_price_list", "sale_price_list", "ecommerce_warehouse")
LIVE_JOB_STATUSES = (JobStatus.QUEUED, JobStatus.STARTED, JobStatus.DEFERRED, JobStatus.SCHEDULED)


def get_missing_settings() -> list:
	settings = frappe.get_cached_doc("Commera Settings")
	return [
		settings.meta.get_label(fieldname) for fieldname in REQUIRED_SETTINGS if not settings.get(fieldname)
	]


def check_import_settings():
	if missing := get_missing_settings():
		frappe.throw(
			_("Set {0} in Commera Settings before importing items from ERPNext.").format(", ".join(missing)),
			title=_("Store Not Set Up"),
		)


def get_importable_items(search: str | None = None) -> tuple[list, list]:
	"""Items that can become products, and those that cannot with the reason."""
	item = frappe.qb.DocType("Item")
	configurator = frappe.qb.DocType("Style Attribute Configurator")
	size_row = frappe.qb.DocType("Color Size Item")
	query = (
		frappe.qb.from_(item)
		.left_join(configurator)
		.on(configurator.item_template == item.name)
		.left_join(size_row)
		.on(size_row.item_code == item.name)
		.select(
			item.name.as_("item_code"),
			item.item_name,
			item.item_group,
			item.image,
			item.has_variants,
			item.variant_based_on,
		)
		.where((item.disabled == 0) & (item.is_sales_item == 1))
		.where(item.variant_of.isnull() | (item.variant_of == ""))
		.where(configurator.name.isnull() & size_row.name.isnull())
		.orderby(item.item_name)
	)
	if search:
		query = query.where(item.item_name.like(f"%{search}%") | item.name.like(f"%{search}%"))
	rows = query.run(as_dict=True)

	sellable_templates = set(
		get_rows(
			"Item",
			"variant_of",
			[row.item_code for row in rows if row.has_variants],
			["variant_of"],
			filters={"disabled": 0},
		).keys()
	)
	importable, skipped = [], []
	for row in rows:
		if reason := get_skip_reason(row, sellable_templates):
			skipped.append({"item_code": row.item_code, "item_name": row.item_name, "reason": reason})
		else:
			importable.append(row)
	return importable, skipped


def get_skip_reason(row, sellable_templates: set) -> str | None:
	if not row.has_variants:
		return None
	if row.variant_based_on == "Manufacturer":
		return _("Its variants are based on manufacturers, which the store cannot show as options.")
	if row.item_code not in sellable_templates:
		return _("It has no enabled variants to sell.")
	return None


def get_rows(doctype: str, fieldname: str, values: list, fields: list, filters: dict | None = None) -> dict:
	"""Rows whose `fieldname` is one of `values`, grouped by that value, in IN (...) sized batches."""
	grouped = {}
	for chunk in create_batch(list(dict.fromkeys(values)), IN_CLAUSE_CHUNK_SIZE):
		for row in frappe.get_all(
			doctype,
			filters={**(filters or {}), fieldname: ["in", chunk]},
			fields=list(dict.fromkeys([fieldname, *fields])),
			order_by="idx asc" if frappe.get_meta(doctype).istable else "creation asc",
		):
			grouped.setdefault(row[fieldname], []).append(row)
	return grouped


def plan_products(item_codes: list) -> list:
	"""How each Item becomes a product: its kind, option axis and the size rows of every option."""
	items = get_rows("Item", "name", item_codes, ["item_name", "item_group", "image", "has_variants"])
	templates = [item_code for item_code, (row,) in items.items() if row.has_variants]
	attributes_by_template = get_rows(
		"Item Variant Attribute", "parent", templates, ["attribute"], filters={"parenttype": "Item"}
	)
	variants_by_template = get_rows(
		"Item", "variant_of", templates, ["name", "image"], filters={"disabled": 0}
	)
	values_by_variant = get_rows(
		"Item Variant Attribute",
		"parent",
		[variant.name for variants in variants_by_template.values() for variant in variants],
		["attribute", "attribute_value"],
		filters={"parenttype": "Item"},
	)

	plans = []
	for item_code in item_codes:
		if item_code not in items:
			continue
		(item,) = items[item_code]
		attributes = [row.attribute for row in attributes_by_template.get(item_code, [])]
		plan = {
			"item_code": item_code,
			"item_name": item.item_name,
			"item_group": item.item_group,
			"image": item.image,
			"kind": get_kind(item.has_variants, attributes),
			"attributes": attributes,
		}
		plan["option_attribute"] = get_option_attribute(plan["kind"], attributes)
		plan["options"] = get_options(plan, variants_by_template.get(item_code, []), values_by_variant)
		plans.append(plan)
	return plans


def get_kind(has_variants, attributes: list) -> str:
	if not has_variants:
		return "plain"
	has_colour = any(attribute in COLOUR_ATTRIBUTES for attribute in attributes)
	has_size = SIZE_ATTRIBUTE in attributes
	if has_colour and has_size:
		return "colour_size"
	if has_size:
		return "size_only"
	if has_colour:
		return "colour_only"
	return "other_attributes"


def get_option_attribute(kind: str, attributes: list) -> str:
	if kind in ("plain", "size_only"):
		return DEFAULT_OPTION_ATTRIBUTE
	if kind in ("colour_size", "colour_only"):
		return next(attribute for attribute in attributes if attribute in COLOUR_ATTRIBUTES)
	return attributes[0]


def get_options(plan: dict, variants: list, values_by_variant: dict) -> dict:
	"""{option: {"image", "sizes": [(label, item_code)]}}. Every attribute but the option axis joins into
	the size label, Size first ("128 GB / Blue"); a variant with none of them is "One Size"."""
	if plan["kind"] == "plain":
		return {
			DEFAULT_OPTION_VALUE: {"image": plan["image"], "sizes": [(DEFAULT_SIZE_VALUE, plan["item_code"])]}
		}

	option_attribute = plan["option_attribute"]
	label_attributes = sorted(
		(attribute for attribute in plan["attributes"] if attribute != option_attribute),
		key=lambda attribute: attribute != SIZE_ATTRIBUTE,
	)
	options = {}
	for variant in variants:
		values = {row.attribute: row.attribute_value for row in values_by_variant.get(variant.name, [])}
		option = (
			DEFAULT_OPTION_VALUE
			if option_attribute == DEFAULT_OPTION_ATTRIBUTE
			else values.get(option_attribute)
		)
		if not option:
			continue
		label = " / ".join(values[attribute] for attribute in label_attributes if values.get(attribute))
		entry = options.setdefault(option, {"image": None, "sizes": []})
		entry["image"] = entry["image"] or variant.image
		entry["sizes"].append((label or DEFAULT_SIZE_VALUE, variant.name))
	for entry in options.values():
		entry["image"] = entry["image"] or plan["image"]
	return options


def get_preview(search: str | None, start: int, page_length: int) -> dict:
	importable, skipped = get_importable_items(search)
	plans = plan_products([row.item_code for row in importable[start : start + page_length]])
	item_codes_by_plan = {
		plan["item_code"]: [
			item_code for entry in plan["options"].values() for _label, item_code in entry["sizes"]
		]
		for plan in plans
	}
	all_item_codes = [item_code for item_codes in item_codes_by_plan.values() for item_code in item_codes]
	rates = {} if get_missing_settings() else get_selling_rates(all_item_codes)
	stock = get_ecommerce_stock(all_item_codes)

	items = []
	for plan in plans:
		item_codes = item_codes_by_plan[plan["item_code"]]
		prices = [rates[item_code] for item_code in item_codes if item_code in rates]
		items.append(
			{
				"item_code": plan["item_code"],
				"item_name": plan["item_name"],
				"item_group": plan["item_group"],
				"kind": plan["kind"],
				"image": plan["image"],
				"price": min(prices) if prices else None,
				"stock": sum(stock.get(item_code, 0) for item_code in item_codes),
				"attributes": plan["attributes"],
				"preselected": True,
			}
		)
	return {"items": items, "skipped": skipped, "total": len(importable)}


class ImportAlreadyRunningError(frappe.ValidationError):
	pass


def get_selection_key(item_codes: list | None) -> str:
	"""What an import was started for, so a restart can tell the same items from other ones (None is every
	item). A digest, not the codes, because the status rides every progress update to the browser."""
	if item_codes is None:
		return "all"
	return hashlib.sha256("\n".join(sorted(set(item_codes))).encode()).hexdigest()


def queue_import(item_codes: list | None) -> dict:
	"""One import at a time. A second start for the same items picks up the running import. One for
	other items is refused: answering with the running import showed its result as theirs."""
	selection = get_selection_key(item_codes)
	if is_job_enqueued(JOB_ID) and (running := frappe.cache.get_value(status_key(JOB_ID))):
		if running.get("selection") == selection:
			return {"job_id": JOB_ID, "log": running["log"]}
		frappe.throw(
			_("An import is already running. Wait for it to finish, then import these items."),
			ImportAlreadyRunningError,
		)

	log = create_configurator_log()
	set_status(JOB_ID, get_new_progress("queued", log.name, total=len(item_codes or []), selection=selection))
	frappe.enqueue(
		import_items,
		queue="long",
		timeout=JOB_TIMEOUT,
		job_id=JOB_ID,
		deduplicate=True,
		enqueue_after_commit=True,
		item_codes=item_codes,
		log_name=log.name,
		import_id=JOB_ID,
	)
	return {"job_id": JOB_ID, "log": log.name}


def import_items(item_codes: list | None, log_name: str, import_id: str = JOB_ID):
	"""Background job. `import_id` is the job id: enqueue keeps `job_id` for itself."""
	importable, _skipped = get_importable_items()
	importable_codes = [row.item_code for row in importable]
	requested = importable_codes if item_codes is None else list(dict.fromkeys(item_codes))
	requested_codes = set(requested)
	importable_codes = [item_code for item_code in importable_codes if item_code in requested_codes]
	skipped_count = len(requested) - len(importable_codes)

	progress = get_new_progress(
		"running", log_name, total=len(requested), selection=get_selection_key(item_codes)
	)
	progress.update(done=skipped_count, skipped=skipped_count)
	set_status(import_id, progress)

	ensure_attribute_exists(DEFAULT_OPTION_ATTRIBUTE, DEFAULT_OPTION_VALUE, "STD")
	log = frappe.get_doc(LOG_DOCTYPE, log_name)
	log.flags.ignore_permissions = True
	webshop_counts = {}
	for batch in create_batch(importable_codes, BATCH_SIZE):
		created = import_batch(plan_products(batch), log, progress["failed"])
		for key, count in apply_webshop_extras(
			[plan["item_code"] for plan, _configurator in created]
		).items():
			webshop_counts[key] = webshop_counts.get(key, 0) + count
		# nosemgrep: frappe-manual-commit  # job checkpoint, a crash keeps the products already made
		frappe.db.commit()
		progress["created"] += len(created)
		progress["done"] += len(batch)
		set_status(import_id, progress)

	if webshop_counts:
		log.add_comment("Info", frappe.as_json({"webshop": webshop_counts}))
	progress["status"] = "done"
	set_status(import_id, progress)


def get_failure_message(error, item_code):
	"""A refusal (ValidationError) is already written for the seller. Anything else is a bug: its text goes
	to the error log, and the seller is told the plain consequence."""
	if isinstance(error, frappe.ValidationError) and cstr(error):
		return cstr(error)
	frappe.log_error(f"ERPNext import of {item_code}")
	return _("Something went wrong with this item. Run the import again to retry it.")


def import_batch(plans: list, log, failed: list) -> list:
	created = []
	for plan in plans:
		frappe.db.savepoint("erpnext_import")
		try:
			configurator = add_product(plan)
		except Exception as error:
			frappe.db.rollback(save_point="erpnext_import")
			failed.append(
				{
					"item_code": plan["item_code"],
					"item_name": plan["item_name"],
					"error": get_failure_message(error, plan["item_code"]),
				}
			)
			continue
		frappe.db.release_savepoint("erpnext_import")
		created.append((plan, configurator))

	if created:
		add_option_images(created)
		add_first_collections([plan for plan, _configurator in created])
		for _plan, configurator in created:
			log.append(
				"configurators",
				{
					"style_attribute_configurator": configurator.name,
					"variants_created": configurator.get_total_variants(),
				},
			)
		log.save()
	return created


def add_product(plan: dict):
	configurator = frappe.new_doc("Style Attribute Configurator")
	configurator.item_template = plan["item_code"]
	configurator.item_attribute = plan["option_attribute"]
	configurator.flags.skip_variant_generation = True
	configurator.insert()

	# generate_variants keeps only the Size value, so a third attribute would merge variants into one size.
	if plan["kind"] == "colour_size" and len(plan["attributes"]) == 2:
		configurator.generate_variants(skip_disabled=True)
		return configurator

	for option, entry in plan["options"].items():
		variant = frappe.new_doc(PRODUCT_DOCTYPE)
		variant.configurator = configurator.name
		variant.item_style = plan["item_code"]
		variant.attribute_value = option
		variant.attribute_name = option
		variant.display_name = plan["item_name"]
		variant.is_published = 0
		for label, item_code in entry["sizes"]:
			variant.append("sizes", {"size": label, "item_code": item_code})
		variant.insert()
	return configurator


def add_option_images(created: list):
	plan_by_configurator = {configurator.name: plan for plan, configurator in created}
	variants = frappe.get_all(
		PRODUCT_DOCTYPE,
		filters={"configurator": ["in", list(plan_by_configurator)]},
		fields=["name", "configurator", "attribute_value"],
	)
	image_by_variant = {}
	for variant in variants:
		option = plan_by_configurator[variant.configurator]["options"].get(variant.attribute_value)
		if option and option["image"]:
			image_by_variant[variant.name] = option["image"]
	add_first_child_rows(PRODUCT_DOCTYPE, "images", "Website Slideshow Item", "image", image_by_variant)


def add_first_collections(plans: list):
	if not frappe.get_meta("Item").has_field(COLLECTIONS_FIELD):
		return
	item_templates = [plan["item_code"] for plan in plans]
	with_rows = get_rows(
		PRODUCT_COLLECTION, "parent", item_templates, ["item_group"], filters={"parenttype": "Item"}
	)
	add_first_child_rows(
		"Item",
		COLLECTIONS_FIELD,
		PRODUCT_COLLECTION,
		"item_group",
		{plan["item_code"]: plan["item_group"] for plan in plans if plan["item_code"] not in with_rows},
	)


def add_first_child_rows(
	parenttype: str, parentfield: str, doctype: str, fieldname: str, value_by_parent: dict
):
	"""One row per parent in one insert, as the add_products_to_their_collection patch does."""
	if not value_by_parent:
		return
	timestamp = now()
	user = frappe.session.user
	frappe.db.bulk_insert(
		doctype,
		fields=[
			"name",
			"creation",
			"modified",
			"owner",
			"modified_by",
			"idx",
			"parent",
			"parentfield",
			"parenttype",
			fieldname,
		],
		values=[
			(
				frappe.generate_hash(length=10),
				timestamp,
				timestamp,
				user,
				user,
				1,
				parent,
				parentfield,
				parenttype,
				value,
			)
			for parent, value in value_by_parent.items()
		],
	)


def publish_imported_products(log: str) -> dict:
	"""Publish all for one ERPNext import, by the same rules as the spreadsheet import's."""
	if not frappe.db.exists(LOG_DOCTYPE, log):
		frappe.throw(_("No such import."), frappe.DoesNotExistError)
	configurators = frappe.get_all(
		"Style Attribute Configurator Log Table",
		filters={"parent": log, "parenttype": LOG_DOCTYPE},
		pluck="style_attribute_configurator",
	)
	drafts = [
		variant
		for variants in get_rows(
			PRODUCT_DOCTYPE,
			"configurator",
			configurators,
			["name", "item_style", "attribute_value"],
			filters={"is_published": 0},
		).values()
		for variant in variants
	]
	return publish_drafts(drafts)


def get_new_progress(status: str, log_name: str, total: int = 0, selection: str | None = None) -> dict:
	return {
		"selection": selection,
		"status": status,
		"done": 0,
		"total": total,
		"created": 0,
		"skipped": 0,
		"failed": [],
		"log": log_name,
	}


def get_status(job_id: str) -> dict:
	progress = frappe.cache.get_value(status_key(job_id))
	if not progress:
		frappe.throw(_("No such import."), frappe.DoesNotExistError)
	if progress["status"] in ("queued", "running") and get_job_status(job_id) not in LIVE_JOB_STATUSES:
		progress["status"] = "failed"
	return progress


def set_status(job_id: str, progress: dict):
	frappe.cache.set_value(status_key(job_id), progress, expires_in_sec=STATUS_SECONDS)
	frappe.publish_realtime("commera_erpnext_import", progress, user=frappe.session.user)


def status_key(job_id: str) -> str:
	return f"commera:erpnext_import:{job_id}"
