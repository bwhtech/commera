import frappe
from frappe import _
from frappe.utils import cstr
from frappe.utils.html_utils import sanitize_html

from commera.api.admin.catalog import create_collection, save_variant_collections
from commera.commera_ecommerce.doctype.commera_settings.navbar.navbar_manager import create_node
from commera.commera_ecommerce.doctype.ecommerce_category.ecommerce_category import build_listing_href
from commera.commera_ecommerce.doctype.shopify_record_link.shopify_record_link import (
	get_link,
	get_linked_name,
	save_link,
)
from commera.sdk.catalog import get_product_collection
from commera.shopify.bulk import get_children
from commera.shopify.files import download_image
from commera.shopify.importers.base import CREATED, SKIPPED, UPDATED, ResourceImporter, to_system_datetime
from commera.shopify.queries import COLLECTION_QUERIES
from commera.shopify.redirects import save_redirects

LANGUAGE = "en"


class CollectionImporter(ResourceImporter):
	"""A Shopify collection becomes a Commera collection (Item Group). Smart collections arrive with
	their current products, so they become fixed lists."""

	resource = "Collections"
	queries = COLLECTION_QUERIES
	# Shopify keeps a collection's updatedAt when its text or SEO changes, and collections are few,
	# so every run reads them all and compares the text itself.
	supports_changed_filter = False

	def __init__(self, runner):
		super().__init__(runner)
		self.redirects = {}
		self.context.setdefault("collections_by_product", {})

	def import_record(self, collection: dict) -> str:
		link = get_link(collection["id"])
		if link:
			item_group = link.reference_name
			menu_slug = (get_product_collection(item_group) or {}).get("handle")
		else:
			item_group, menu_slug = self.create_collection(collection)
		# The old /collections/<handle> link opens the collection's own listing.
		self.redirects[f"collections/{collection['handle']}"] = build_listing_href(
			menu_slug, [item_group], LANGUAGE
		)

		if collection.get("ruleSet"):
			self.warn(collection, _("Smart collection: imported with its current products as a fixed list."))
		self.save_image(collection, item_group)
		text_changed = self.save_storefront_text(collection, item_group)

		for product in get_children(collection, "Product"):
			self.context["collections_by_product"].setdefault(product["id"], []).append(item_group)

		if not link:
			outcome = CREATED
		elif text_changed or not self.is_unchanged(link, collection):
			outcome = UPDATED
		else:
			outcome = SKIPPED
		save_link(
			collection["id"],
			self.resource,
			"Item Group",
			item_group,
			to_system_datetime(collection.get("updatedAt")),
		)
		return outcome

	def create_collection(self, collection: dict) -> tuple[str, str | None]:
		"""Returns the new collection and the slug of its menu tab, when the import adds one. The
		storefront menu is read once per job, so a tab added during this run is not found later."""
		item_group = create_collection(get_free_collection_name(collection["title"]))["name"]
		if not self.settings.add_collections_to_menu:
			return item_group, None
		return item_group, create_node(None, collection["title"], "Item Group", [item_group]).route_slug

	def save_image(self, collection: dict, item_group: str) -> None:
		image_url = (collection.get("image") or {}).get("url")
		if image_url and not frappe.db.get_value("Item Group", item_group, "image"):
			file_url = download_image(
				image_url, "Item Group", item_group, self.context.setdefault("files", {})
			)
			frappe.db.set_value("Item Group", item_group, "image", file_url)

	def save_storefront_text(self, collection: dict, item_group: str) -> bool:
		"""Returns whether the text changed."""
		seo = collection.get("seo") or {}
		description = self.get_html_with_local_images(
			collection, collection.get("descriptionHtml"), "Item Group", item_group
		)
		text = {
			"custom_description": sanitize_html(description) or None,
			"custom_meta_title": cstr(seo.get("title")).strip()[:140] or None,
			"custom_meta_description": cstr(seo.get("description")).strip() or None,
		}
		saved = frappe.db.get_value("Item Group", item_group, list(text), as_dict=True)
		if all((saved.get(field) or None) == value for field, value in text.items()):
			return False
		frappe.db.set_value("Item Group", item_group, text)
		return True

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
