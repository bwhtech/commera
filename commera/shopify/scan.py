from collections import Counter

import frappe
from frappe import _

from commera.shopify.bulk import get_children
from commera.shopify.client import ShopifyApiError
from commera.shopify.importers.base import fetch_with_fallback
from commera.shopify.importers.store import save_shop_details
from commera.shopify.mapping import plan_product
from commera.shopify.queries import COLLECTION_QUERIES, COUNT_QUERIES, PRODUCT_QUERIES, SHOP_QUERY
from commera.utils import get_store_currency

NOT_IMPORTED_RESOURCES = ("Orders", "Discounts", "Gift cards", "Blogs")
MAX_EXAMPLES = 5


class StoreScanner:
	"""Reads the store without writing to Commera, and reports what will not fit."""

	def __init__(self, client, settings):
		self.client = client
		self.settings = settings

	def scan(self) -> dict:
		shop = self.client.execute(SHOP_QUERY)["shop"]
		save_shop_details(self.settings, shop)
		products = fetch_with_fallback(self.client, PRODUCT_QUERIES)
		collections = fetch_with_fallback(self.client, COLLECTION_QUERIES)

		counts = self.get_counts()
		findings = get_store_findings(shop, counts)
		findings += get_product_findings(products, self.settings.page_option_name_keys)
		findings += get_collection_findings(collections)
		return {
			"shop": {
				"name": shop.get("name"),
				"domain": (shop.get("primaryDomain") or {}).get("host"),
				"currency": shop.get("currencyCode"),
			},
			"counts": counts,
			"findings": findings,
		}

	def get_counts(self) -> dict:
		counts = {}
		for resource, query in COUNT_QUERIES.items():
			try:
				counts[resource] = next(iter(self.client.execute(query).values()))["count"]
			except ShopifyApiError:
				# A missing scope or a field this API version lacks: the count is unknown, not zero.
				counts[resource] = None
		return counts


def finding(
	level: str, title: str, detail: str, examples: list | None = None, count: int | None = None
) -> dict:
	examples = examples or []
	return {
		"level": level,
		"title": title,
		"detail": detail,
		"count": len(examples) if count is None else count,
		"examples": examples[:MAX_EXAMPLES],
	}


def get_store_findings(shop: dict, counts: dict) -> list[dict]:
	findings = []
	store_currency = get_store_currency()
	if shop.get("currencyCode") and shop["currencyCode"] != store_currency:
		findings.append(
			finding(
				"warning",
				_("Different currency"),
				_("Shopify sells in {0} and this store sells in {1}. Prices are copied as numbers.").format(
					shop["currencyCode"], store_currency
				),
				count=1,
			)
		)
	if not frappe.db.get_single_value("Commera Settings", "ecommerce_warehouse"):
		findings.append(
			finding(
				"warning",
				_("No Ecommerce Warehouse"),
				_("Set it in Commera Settings to import stock."),
				count=1,
			)
		)
	for resource in NOT_IMPORTED_RESOURCES:
		if counts.get(resource):
			findings.append(
				finding(
					"warning",
					_("{0} are not imported").format(resource),
					_("The import does not bring these over yet."),
					count=counts[resource],
				)
			)
	return findings


def get_product_findings(products: list[dict], page_option_names: list[str]) -> list[dict]:
	"""Each check lists the titles of the products it applies to."""
	joined, single_page, no_images, other_media, tagged, sell_out_of_stock = [], [], [], [], [], []
	for product in products:
		plan = plan_product(product, page_option_names)
		variants = get_children(product, "ProductVariant")
		title = product.get("title")
		if plan.joined_size_options:
			joined.append(title)
		if not plan.has_page_option and len(plan.size_options) == 1:
			single_page.append(title)
		if not get_children(product, "MediaImage"):
			no_images.append(title)
		if get_children(product, "Video", "ExternalVideo", "Model3d"):
			other_media.append(title)
		if product.get("tags"):
			tagged.append(title)
		if any(variant.get("inventoryPolicy") == "CONTINUE" for variant in variants):
			sell_out_of_stock.append(title)

	repeated_titles = [
		title for title, count in Counter(p.get("title") for p in products).items() if count > 1
	]
	checks = [
		(
			"warning",
			_("More than two options"),
			_("The options that do not make pages are joined into one size label, for example M / Cotton."),
			joined,
		),
		(
			"info",
			_("One page with a size picker"),
			_("No option is a colour, so the product gets one page and its option values become sizes."),
			single_page,
		),
		("warning", _("No images"), _("Pages without images stay unpublished."), no_images),
		("warning", _("Videos or 3D models"), _("Only images are imported."), other_media),
		("warning", _("Product tags"), _("Commera has no product tags. Tags are not imported."), tagged),
		(
			"warning",
			_("Sells when out of stock"),
			_("Commera stops selling at zero stock."),
			sell_out_of_stock,
		),
		(
			"info",
			_("Repeated titles"),
			_("Product codes get the Shopify handle added. Titles stay the same."),
			repeated_titles,
		),
	]
	return [finding(level, title, detail, examples) for level, title, detail, examples in checks if examples]


def get_collection_findings(collections: list[dict]) -> list[dict]:
	collections_by_product = Counter(
		product["id"] for collection in collections for product in get_children(collection, "Product")
	)
	in_several = [product_id for product_id, count in collections_by_product.items() if count > 1]
	smart = [collection.get("title") for collection in collections if collection.get("ruleSet")]

	findings = []
	if in_several:
		findings.append(
			finding(
				"warning",
				_("Products in several collections"),
				_("A Commera product has one collection. The first Shopify collection is kept."),
				count=len(in_several),
			)
		)
	if smart:
		findings.append(
			finding(
				"info",
				_("Smart collections"),
				_("They are imported with their current products as fixed lists."),
				smart,
			)
		)
	return findings
