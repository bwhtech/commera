import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from commera.api.admin.catalog import (
	DEFAULT_OPTION_ATTRIBUTE,
	DEFAULT_OPTION_VALUE,
	DEFAULT_SIZE_VALUE,
	SIZE_ATTRIBUTE,
	create_collection,
	create_product,
	ensure_attribute_exists,
	get_variant_items_by_pair,
)
from commera.commera_ecommerce.doctype.shopify_record_link.shopify_record_link import (
	get_link,
	get_linked_name,
	save_link,
)
from commera.shopify.importers.base import CREATED, SKIPPED, UPDATED, ResourceImporter, to_system_datetime
from commera.shopify.importers.product_pages import ProductPageWriter
from commera.shopify.mapping import plan_product
from commera.shopify.queries import PRODUCT_QUERIES
from commera.shopify.redirects import save_redirects

FALLBACK_COLLECTION = "Shopify"
WEIGHT_UNITS = {"GRAMS": "Gram", "KILOGRAMS": "Kg", "OUNCES": "Ounce", "POUNDS": "Pound"}


class ProductImporter(ResourceImporter):
	"""A Shopify product becomes an Item template with one product page per value of the page option,
	and one size Item per Shopify variant."""

	resource = "Products"
	queries = PRODUCT_QUERIES

	def __init__(self, runner):
		super().__init__(runner)
		self.redirects = {}
		self.files = self.context.setdefault("files", {})
		self.has_warehouse = bool(frappe.db.get_single_value("Commera Settings", "ecommerce_warehouse"))
		if self.settings.import_inventory and not self.has_warehouse:
			runner.run.add_issue(
				self.resource,
				_("Stock was not imported: set the Ecommerce Warehouse in Commera Settings."),
				"Warning",
			)

	def import_record(self, product: dict) -> str:
		link = get_link(product["id"])
		if link and link.reference_doctype == "Item":
			if self.is_unchanged(link, product):
				return SKIPPED
			item_template = link.reference_name
			self.update_product(item_template, product)
			outcome = UPDATED
		else:
			item_template = self.create_product(product)
			outcome = CREATED

		save_link(
			product["id"], self.resource, "Item", item_template, to_system_datetime(product.get("updatedAt"))
		)
		return outcome

	def create_product(self, product: dict) -> str:
		plan = plan_product(product, self.settings.page_option_name_keys)
		if not plan.pages:
			frappe.throw(_("The product has no variants."))
		if plan.joined_size_options:
			self.warn(
				product,
				_("Options {0} were joined into one size label.").format(", ".join(plan.size_options)),
			)

		option_attribute = self.get_option_attribute(plan)
		item_template = create_product(
			title=product["title"],
			item_code=get_free_item_code(product),
			collection=self.get_collection(product),
			option_attribute=option_attribute,
			size_attribute=SIZE_ATTRIBUTE,
			option_sizes=plan.get_option_sizes(DEFAULT_OPTION_VALUE),
		)["name"]
		# Saving the template copies its fields down to the size Items, so it goes first.
		update_template(item_template, product)

		items_by_pair = get_variant_items_by_pair(item_template, option_attribute or DEFAULT_OPTION_ATTRIBUTE)
		for page_value, rows in plan.pages.items():
			option = page_value if plan.has_page_option else DEFAULT_OPTION_VALUE
			for row in rows:
				item = items_by_pair[(option.casefold(), (row.size or DEFAULT_SIZE_VALUE).casefold())]
				save_link(row.variant["id"], "Product Variants", "Item", item.name)
				update_size_item(item.name, row.variant)

		if all(not is_tracked(row.variant) for rows in plan.pages.values() for row in rows):
			mark_untracked(item_template)

		writer = ProductPageWriter(self, product, plan, item_template)
		writer.write_new_pages()
		self.redirects.update(writer.redirects)
		return item_template

	def update_product(self, item_template: str, product: dict) -> None:
		update_template(item_template, product)
		plan = plan_product(product, self.settings.page_option_name_keys)
		missing = [
			row.variant.get("title")
			for rows in plan.pages.values()
			for row in rows
			if not get_linked_name(row.variant["id"])
		]
		if missing:
			self.warn(
				product,
				_("New Shopify variants were not added: {0}. Add them in Commera.").format(
					", ".join(missing)
				),
			)
		ProductPageWriter(self, product, plan, item_template).update_pages()

	def get_option_attribute(self, plan) -> str | None:
		if not plan.has_page_option:
			return None
		attribute = cstr(self.settings.option_attribute).strip() or "Color"
		return ensure_attribute_exists(attribute, DEFAULT_OPTION_VALUE, "STD")

	def get_collection(self, product: dict) -> str:
		item_groups = self.context.get("collections_by_product", {}).get(product["id"])
		if item_groups:
			return item_groups[0]
		if self.settings.default_collection:
			return self.settings.default_collection
		if not frappe.db.exists("Item Group", FALLBACK_COLLECTION):
			create_collection(FALLBACK_COLLECTION)
		return FALLBACK_COLLECTION

	def finish(self) -> None:
		save_redirects(self.redirects)


def get_free_item_code(product: dict) -> str:
	"""Shopify titles repeat and Item codes cannot. An Item code also cannot equal a collection name."""
	title = cstr(product["title"]).strip()
	numeric_id = cstr(product["id"]).rsplit("/", 1)[-1]
	for candidate in (title, f"{title} ({product.get('handle')})", f"{title} ({numeric_id})"):
		candidate = candidate[:140]
		if not frappe.db.exists("Item", candidate) and not frappe.db.exists("Item Group", candidate):
			return candidate
	frappe.throw(_("No free product code for {0}").format(title))


def update_template(item_template: str, product: dict) -> None:
	item = frappe.get_doc("Item", item_template)
	item.item_name = cstr(product["title"]).strip() or item.item_name
	item.description = product.get("descriptionHtml") or item.description
	item.disabled = cint(product.get("status") == "ARCHIVED")
	if product.get("vendor"):
		item.brand = ensure_brand(product["vendor"])
	item.save()


def ensure_brand(vendor: str) -> str:
	vendor = cstr(vendor).strip()[:140]
	if not frappe.db.exists("Brand", vendor):
		frappe.get_doc({"doctype": "Brand", "brand": vendor}).insert(ignore_permissions=True)
	return vendor


def update_size_item(item_code: str, variant: dict) -> None:
	weight = ((variant.get("inventoryItem") or {}).get("measurement") or {}).get("weight") or {}
	if flt(weight.get("value")) and WEIGHT_UNITS.get(weight.get("unit")):
		frappe.db.set_value(
			"Item",
			item_code,
			{"weight_per_unit": flt(weight["value"]), "weight_uom": WEIGHT_UNITS[weight["unit"]]},
		)

	barcode = cstr(variant.get("barcode")).strip()
	if barcode and not frappe.db.exists("Item Barcode", {"barcode": barcode}):
		item = frappe.get_doc("Item", item_code)
		item.append("barcodes", {"barcode": barcode})
		item.save()


def is_tracked(variant: dict) -> bool:
	return bool((variant.get("inventoryItem") or {}).get("tracked", True))


def mark_untracked(item_template: str) -> None:
	"""Commera sells an Item that is not a stock item without a stock check. A new product has no
	stock ledger yet, so the flag can still change."""
	item_codes = [item_template, *frappe.get_all("Item", {"variant_of": item_template}, pluck="name")]
	for item_code in item_codes:
		frappe.db.set_value("Item", item_code, "is_stock_item", 0)
