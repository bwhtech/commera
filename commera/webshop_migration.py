import re

import frappe
from frappe.query_builder.functions import Count
from frappe.utils import create_batch, flt, now, strip_html

from commera.commera_ecommerce.doctype.product_review.product_review import (
	get_review_name,
	write_variant_rating,
)
from commera.utils import IN_CLAUSE_CHUNK_SIZE, get_rows

PRODUCT_DOCTYPE = "Style Attribute Variant"
WEBSHOP_DOCTYPES = ("Website Item", "Item Review", "Wishlist")
PRODUCT_ROUTE_PREFIX = "products/"
DOCUMENT_FIELDS = ["name", "creation", "modified", "owner", "modified_by"]
WEBSITE_ITEM_FIELDS = ["name", "item_code", "route", "slideshow", "website_image", "web_long_description"]


def has_webshop_data() -> bool:
	# Webshop needs frappe/payments, whose "Payment Gateways" module clashes with Commera's, so webshop is
	# out of installed_apps before Commera installs; its tables stay behind.
	return all(frappe.db.table_exists(doctype) for doctype in WEBSHOP_DOCTYPES)


def get_webshop_rows(doctype: str, fieldname: str, values, fields: list[str], **conditions) -> list[dict]:
	# The first migrate after webshop leaves installed_apps deletes its DocType records but not its
	# tables, so these reads go straight to the tables and never through meta (get_all, get_value).
	table = frappe.qb.DocType(doctype)
	rows = []
	for chunk in create_batch(list(dict.fromkeys(values)), IN_CLAUSE_CHUNK_SIZE):
		query = frappe.qb.from_(table).select(*[table[field] for field in fields])
		query = query.where(table[fieldname].isin(chunk))
		for condition_field, value in conditions.items():
			query = query.where(table[condition_field] == value)
		rows += query.run(as_dict=True)
	return rows


def get_webshop_published_items() -> set[str] | None:
	"""Item codes to preselect for import, or None when webshop is not installed."""
	if not has_webshop_data():
		return None
	website_item = frappe.qb.DocType("Website Item")
	website_items = (
		frappe.qb.from_(website_item)
		.select(website_item.item_code, website_item.variant_of)
		.where(website_item.published == 1)
		.run(as_dict=True)
	)
	return {website_item.variant_of or website_item.item_code for website_item in website_items}


def get_webshop_store_defaults() -> dict:
	if not has_webshop_data():
		return {}
	settings = frappe.db.get_singles_dict("Webshop Settings")
	return {
		"company": settings.company,
		"price_list": settings.price_list,
		"warehouse": get_most_used_website_warehouse(settings.company),
	}


def get_most_used_website_warehouse(company: str | None) -> str | None:
	if not company:
		return None
	website_item = frappe.qb.DocType("Website Item")
	warehouse = frappe.qb.DocType("Warehouse")
	rows = (
		frappe.qb.from_(website_item)
		.join(warehouse)
		.on(warehouse.name == website_item.website_warehouse)
		.select(website_item.website_warehouse)
		.where((website_item.published == 1) & (warehouse.company == company) & (warehouse.is_group == 0))
		.groupby(website_item.website_warehouse)
		.orderby(Count(website_item.name), order=frappe.qb.desc)
		.limit(1)
		.run()
	)
	return rows[0][0] if rows else None


def apply_webshop_extras(item_codes: list[str]) -> dict:
	"""Bring a batch of imported templates' webshop data across. Safe to run again: it adds nothing twice."""
	if not item_codes or not has_webshop_data():
		return {}

	products_by_template = get_rows(PRODUCT_DOCTYPE, "item_style", item_codes, ["name"])
	if not products_by_template:
		return {}

	products_by_item, item_style_by_product = get_products_by_item(products_by_template)
	website_items = get_published_website_items(item_codes)

	set_product_images(website_items, products_by_item)
	set_product_routes(website_items, products_by_item)
	set_item_descriptions(website_items)
	return {
		"reviews": add_product_reviews(products_by_item, item_style_by_product),
		"wishlist_items": add_wishlist_items(products_by_item),
		"dropped_offers": count_dropped_offers(website_items),
	}


def get_products_by_item(products_by_template: dict) -> tuple[dict, dict]:
	"""Template code -> its first product; every size Item code -> the product it sits in."""
	products_by_item = {template: products[0].name for template, products in products_by_template.items()}
	item_style_by_product = {
		product.name: template for template, products in products_by_template.items() for product in products
	}
	size_rows = get_rows(
		"Color Size Item", "parent", item_style_by_product, ["item_code"], {"parenttype": PRODUCT_DOCTYPE}
	)
	for product, rows in size_rows.items():
		for row in rows:
			products_by_item.setdefault(row.item_code, product)
	return products_by_item, item_style_by_product


def get_published_website_items(item_codes: list[str]) -> list[dict]:
	website_items = {}
	for fieldname in ("item_code", "variant_of"):
		for row in get_webshop_rows("Website Item", fieldname, item_codes, WEBSITE_ITEM_FIELDS, published=1):
			website_items[row.name] = row
	template_codes = set(item_codes)
	# A template's Website Item wins over its variants' for the product they share.
	return sorted(website_items.values(), key=lambda row: row.item_code not in template_codes)


def set_product_images(website_items: list[dict], products_by_item: dict[str, str]):
	slideshow_images = get_rows(
		"Website Slideshow Item",
		"parent",
		[website_item.slideshow for website_item in website_items if website_item.slideshow],
		["image"],
		{"parenttype": "Website Slideshow", "image": ["is", "set"]},
	)
	images_by_product = {}
	for website_item in website_items:
		product = products_by_item.get(website_item.item_code)
		images = [row.image for row in slideshow_images.get(website_item.slideshow, [])]
		images = images or ([website_item.website_image] if website_item.website_image else [])
		if product and images:
			images_by_product.setdefault(product, images)
	if not images_by_product:
		return

	image_row = frappe.qb.DocType("Website Slideshow Item")
	(
		frappe.qb.from_(image_row)
		.delete()
		.where(
			(image_row.parenttype == PRODUCT_DOCTYPE)
			& (image_row.parentfield == "images")
			& image_row.parent.isin(list(images_by_product))
		)
		.run()
	)
	timestamp, user = now(), frappe.session.user
	frappe.db.bulk_insert(
		"Website Slideshow Item",
		fields=[*DOCUMENT_FIELDS, "parent", "parenttype", "parentfield", "idx", "image"],
		values=[
			(
				frappe.generate_hash(length=10),
				timestamp,
				timestamp,
				user,
				user,
				product,
				PRODUCT_DOCTYPE,
				"images",
				index,
				image,
			)
			for product, images in images_by_product.items()
			for index, image in enumerate(images, start=1)
		],
	)


def get_product_route(website_item_route: str | None) -> str:
	return (website_item_route or "").strip("/").removeprefix(PRODUCT_ROUTE_PREFIX)


def set_product_routes(website_items: list[dict], products_by_item: dict[str, str]):
	routes_by_product = {}
	for website_item in website_items:
		product = products_by_item.get(website_item.item_code)
		if product and get_product_route(website_item.route):
			routes_by_product.setdefault(product, get_product_route(website_item.route))
	if not routes_by_product:
		return

	taken_routes = {
		route
		for route, products in get_rows(
			PRODUCT_DOCTYPE, "route", list(routes_by_product.values()), ["name"]
		).items()
		if any(product.name not in routes_by_product for product in products)
	}
	routes_by_product = {
		product: route for product, route in routes_by_product.items() if route not in taken_routes
	}
	for product, route in routes_by_product.items():
		frappe.db.set_value(PRODUCT_DOCTYPE, product, "route", route, update_modified=False)
	add_route_redirects(
		website_item.route.strip("/")
		for website_item in website_items
		if get_product_route(website_item.route) in routes_by_product.values()
	)


def add_route_redirects(website_item_routes):
	"""Old Website Item URLs outside /products/ redirect to the same path under /products/."""
	redirects = {}
	for route in website_item_routes:
		if route.startswith(PRODUCT_ROUTE_PREFIX):
			continue
		top_segment, _, rest = route.partition("/")
		if rest:
			redirects[f"{re.escape(top_segment)}/(.+)"] = f"/{PRODUCT_ROUTE_PREFIX}{top_segment}/\\1"
		else:
			redirects[re.escape(route)] = f"/{PRODUCT_ROUTE_PREFIX}{route}"
	if not redirects:
		return

	website_settings = frappe.get_single("Website Settings")
	new_sources = sorted(set(redirects) - {row.source for row in website_settings.route_redirects})
	if not new_sources:
		return
	for source in new_sources:
		website_settings.append(
			"route_redirects", {"source": source, "target": redirects[source], "redirect_http_status": "301"}
		)
	website_settings.save()


def set_item_descriptions(website_items: list[dict]):
	long_descriptions = {
		website_item.item_code: website_item.web_long_description
		for website_item in website_items
		if strip_html(website_item.web_long_description or "").strip()
	}
	items = get_rows("Item", "name", long_descriptions, ["item_name", "description"])
	for item_code, (item,) in items.items():
		# ERPNext fills a blank description with the item name, so that counts as empty too.
		if strip_html(item.description or "").strip() in ("", item.item_name):
			frappe.db.set_value("Item", item_code, "description", long_descriptions[item_code])


def get_star_rating(rating) -> int:
	"""Webshop's Rating field holds a 0-1 fraction; Product Review wants 1-5 stars."""
	rating = flt(rating)
	stars = round(rating * 5) if rating <= 1 else round(rating)
	return min(5, max(1, stars))


def add_product_reviews(products_by_item: dict[str, str], item_style_by_product: dict[str, str]) -> int:
	reviews = get_webshop_rows(
		"Item Review",
		"item",
		products_by_item,
		["item", "user", "rating", "review_title", "comment", "creation", "modified"],
	)
	rows_by_name = {}
	for review in reviews:
		if not review.user or review.user == "Guest":
			continue
		product = products_by_item[review.item]
		name = get_review_name(product, review.user)
		rows_by_name.setdefault(
			name,
			(
				name,
				review.creation,
				review.modified,
				review.user,
				review.user,
				product,
				item_style_by_product[product],
				get_star_rating(review.rating),
				review.review_title,
				review.comment,
				1,
				0,
			),
		)
	existing_names = get_rows("Product Review", "name", rows_by_name, [])
	new_rows = [row for name, row in rows_by_name.items() if name not in existing_names]
	if not new_rows:
		return 0

	frappe.db.bulk_insert(
		"Product Review",
		fields=[
			*DOCUMENT_FIELDS,
			"variant",
			"item_style",
			"rating",
			"review_title",
			"comment",
			"is_published",
			"verified_purchase",
		],
		values=new_rows,
		ignore_duplicates=True,
	)
	for product in {row[5] for row in new_rows}:
		write_variant_rating(product)
	return len(new_rows)


def add_wishlist_items(products_by_item: dict[str, str]) -> int:
	wishlist_rows = get_webshop_rows(
		"Wishlist Item", "item_code", products_by_item, ["parent", "item_code"], parenttype="Wishlist"
	)
	pairs = {(row.parent, products_by_item[row.item_code]) for row in wishlist_rows}
	saved_rows = get_rows("Commera Wishlist Item", "user", {user for user, _product in pairs}, ["product"])
	existing_pairs = {(user, row.product) for user, rows in saved_rows.items() for row in rows}
	new_pairs = sorted(pairs - existing_pairs)
	if not new_pairs:
		return 0

	timestamp = now()
	frappe.db.bulk_insert(
		"Commera Wishlist Item",
		fields=[*DOCUMENT_FIELDS, "user", "product"],
		values=[
			(frappe.generate_hash(), timestamp, timestamp, user, user, user, product)
			for user, product in new_pairs
		],
		ignore_duplicates=True,
	)
	return len(new_pairs)


def count_dropped_offers(website_items: list[dict]) -> int:
	offers = get_webshop_rows(
		"Website Offer",
		"parent",
		[website_item.name for website_item in website_items],
		["name"],
		parenttype="Website Item",
	)
	return len(offers)
