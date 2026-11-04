import frappe
from frappe import _
from frappe.utils import cstr, flt
from frappe.website.utils import cleanup_page_name

from commera.api.admin.catalog import DEFAULT_OPTION_VALUE
from commera.commera_ecommerce.doctype.shopify_record_link.shopify_record_link import get_linked_name
from commera.shopify.bulk import get_children
from commera.shopify.files import download_image, get_url_key
from commera.shopify.stock import set_stock_levels

PRODUCT_URL_PREFIX = "/en/products/"


class ProductPageWriter:
	"""Images, SEO, routes, publishing, prices and stock of the product pages (Style Attribute
	Variants) of one imported Shopify product."""

	def __init__(self, importer, product: dict, plan, item_template: str):
		self.importer = importer
		self.settings = importer.settings
		self.product = product
		self.plan = plan
		self.item_template = item_template
		self.redirects = {}
		configurator = frappe.db.get_value("Style Attribute Configurator", {"item_template": item_template})
		self.page_names = {
			cstr(row.attribute_value).casefold(): row.name
			for row in frappe.get_all(
				"Style Attribute Variant", {"configurator": configurator}, ["name", "attribute_value"]
			)
		}

	def get_page(self, page_value: str):
		option = page_value if self.plan.has_page_option else DEFAULT_OPTION_VALUE
		return frappe.get_doc("Style Attribute Variant", self.page_names[option.casefold()])

	def write_new_pages(self) -> None:
		if get_children(self.product, "Video", "ExternalVideo", "Model3d"):
			self.importer.warn(
				self.product, _("Videos and 3D models were not imported. Commera pages show images only.")
			)

		for index, (page_value, rows) in enumerate(self.plan.pages.items()):
			page = self.get_page(page_value)
			self.add_images(page, page_value)
			seo = self.product.get("seo") or {}
			page.meta_title = seo.get("title")
			page.meta_description = seo.get("description")
			page.route = get_free_route(
				get_page_route(self.product["handle"], page_value, index == 0), page.name
			)
			page.is_published = self.should_publish(page)
			page.save()
			self.write_prices_and_stock(page, rows)

			if index == 0 and page.route != self.product["handle"]:
				self.redirects[f"en/products/{self.product['handle']}"] = PRODUCT_URL_PREFIX + page.route

	def update_pages(self) -> None:
		for page_value, rows in self.plan.pages.items():
			if (
				page_value if self.plan.has_page_option else DEFAULT_OPTION_VALUE
			).casefold() not in self.page_names:
				continue
			page = self.get_page(page_value)
			if not page.images:
				self.add_images(page, page_value)
				page.save()
			self.write_prices_and_stock(page, rows)

	def should_publish(self, page) -> bool:
		if self.product.get("status") != "ACTIVE" or not self.settings.publish_active_products:
			return False
		if not page.images:
			self.importer.warn(
				self.product, _("{0} has no images, so it was left unpublished.").format(page.name)
			)
			return False
		return True

	def add_images(self, page, page_value: str) -> None:
		for image in self.get_page_images(page_value):
			file_url = download_image(image["url"], "Item", self.item_template, self.importer.files)
			page.append("images", {"image": file_url})

	def get_page_images(self, page_value: str) -> list[dict]:
		"""The page's own variant images first, then product images that no other page claims."""
		media = [
			{"url": media["image"]["url"]}
			for media in get_children(self.product, "MediaImage")
			if (media.get("image") or {}).get("url")
		]
		variant_urls = {
			value: [
				row.variant["image"]["url"] for row in rows if (row.variant.get("image") or {}).get("url")
			]
			for value, rows in self.plan.pages.items()
		}
		if not any(variant_urls.values()):
			return media

		own = list(dict.fromkeys(variant_urls[page_value]))
		claimed = {get_url_key(url) for value, urls in variant_urls.items() for url in urls}
		return [{"url": url} for url in own] + [
			image for image in media if get_url_key(image["url"]) not in claimed
		]

	def write_prices_and_stock(self, page, rows) -> None:
		item_by_variant = {row.variant["id"]: get_linked_name(row.variant["id"]) for row in rows}
		linked_rows = [row for row in rows if item_by_variant[row.variant["id"]]]
		page.save_size_prices(
			[
				{
					"item_code": item_by_variant[row.variant["id"]],
					"default_rate": max(
						flt(row.variant.get("compareAtPrice")), flt(row.variant.get("price"))
					),
					"sale_rate": flt(row.variant.get("price")),
				}
				for row in linked_rows
			]
		)

		if not self.settings.import_inventory or not self.importer.has_warehouse:
			return
		quantities = {
			item_by_variant[row.variant["id"]]: flt(row.variant.get("inventoryQuantity"))
			for row in linked_rows
			if (row.variant.get("inventoryItem") or {}).get("tracked", True)
		}
		if quantities and frappe.db.get_value("Item", self.item_template, "is_stock_item"):
			set_stock_levels(page, quantities)


def get_page_route(handle: str, page_value: str, is_first_page: bool) -> str:
	return handle if is_first_page else f"{handle}-{cleanup_page_name(page_value).replace('_', '-')}"


def get_free_route(route: str, page_name: str) -> str:
	candidate = route
	suffix = 2
	while frappe.db.exists("Style Attribute Variant", {"route": candidate, "name": ("!=", page_name)}):
		candidate = f"{route}-{suffix}"
		suffix += 1
	return candidate
