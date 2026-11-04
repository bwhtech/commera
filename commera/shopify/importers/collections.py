import frappe
from frappe import _
from frappe.utils import cstr

from commera.api.admin.catalog import create_collection, save_variant_collections
from commera.commera_ecommerce.doctype.commera_settings.navbar.navbar_manager import create_node
from commera.commera_ecommerce.doctype.shopify_record_link.shopify_record_link import (
	get_link,
	get_linked_name,
	save_link,
)
from commera.shopify.bulk import get_children
from commera.shopify.files import download_image
from commera.shopify.importers.base import CREATED, SKIPPED, UPDATED, ResourceImporter, to_system_datetime
from commera.shopify.queries import COLLECTION_QUERIES
from commera.shopify.redirects import save_redirects

ALL_PRODUCTS_URL = "/en/products"


class CollectionImporter(ResourceImporter):
	"""A Shopify collection becomes a Commera collection (Item Group). Smart collections arrive with
	their current products, so they become fixed lists."""

	resource = "Collections"
	queries = COLLECTION_QUERIES

	def __init__(self, runner):
		super().__init__(runner)
		self.redirects = {}
		self.context.setdefault("collections_by_product", {})

	def import_record(self, collection: dict) -> str:
		link = get_link(collection["id"])
		item_group = link.reference_name if link else None
		if not item_group:
			item_group = create_collection(get_free_collection_name(collection["title"]))["name"]
			self.add_to_menu(collection, item_group)

		if collection.get("ruleSet"):
			self.warn(collection, _("Smart collection: imported with its current products as a fixed list."))
		self.save_image(collection, item_group)

		for product in get_children(collection, "Product"):
			self.context["collections_by_product"].setdefault(product["id"], []).append(item_group)

		outcome = CREATED if not link else SKIPPED if self.is_unchanged(link, collection) else UPDATED
		save_link(
			collection["id"],
			self.resource,
			"Item Group",
			item_group,
			to_system_datetime(collection.get("updatedAt")),
		)
		return outcome

	def save_image(self, collection: dict, item_group: str) -> None:
		image_url = (collection.get("image") or {}).get("url")
		if image_url and not frappe.db.get_value("Item Group", item_group, "image"):
			file_url = download_image(
				image_url, "Item Group", item_group, self.context.setdefault("files", {})
			)
			frappe.db.set_value("Item Group", item_group, "image", file_url)

	def add_to_menu(self, collection: dict, item_group: str) -> None:
		target = ALL_PRODUCTS_URL
		if self.settings.add_collections_to_menu:
			category = create_node(None, collection["title"], "Item Group", [item_group])
			target = f"{ALL_PRODUCTS_URL}?category={category.route_slug}"
		self.redirects[f"collections/{collection['handle']}"] = target

	def finish(self) -> None:
		save_redirects(self.redirects)
		self.move_imported_products()

	def move_imported_products(self) -> None:
		"""A product imported before its collection, or moved in Shopify, gets its first collection."""
		moved = []
		for product_id, item_groups in self.context["collections_by_product"].items():
			item_template = get_linked_name(product_id)
			if item_template and frappe.db.get_value("Item", item_template, "item_group") != item_groups[0]:
				item = frappe.get_doc("Item", item_template)
				item.item_group = item_groups[0]
				item.save()
				moved.append(item_template)
		if moved:
			save_variant_collections(moved)


def get_free_collection_name(title: str) -> str:
	"""Item Group names must not repeat, and must not equal an Item name."""
	title = cstr(title).strip() or _("Shopify collection")
	candidates = [title, f"{title} Collection"] + [f"{title} Collection {number}" for number in range(2, 100)]
	for candidate in candidates:
		if not frappe.db.exists("Item Group", candidate) and not frappe.db.exists("Item", candidate):
			return candidate
	frappe.throw(_("No free collection name for {0}").format(title))
