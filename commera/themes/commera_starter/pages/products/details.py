from urllib.parse import urlencode

import frappe
from frappe import _

from commera import seo
from commera.localization import get_localization
from commera.sdk import catalog, wishlist
from commera.sdk.format import product_url, url


def get_context(context):
	product = catalog.get_product(frappe.form_dict.get("route"))
	if not product:
		raise frappe.PageDoesNotExistError

	context.product = product
	context.in_wishlist = frappe.session.user != "Guest" and product["id"] in {
		card["id"] for card in wishlist.get_wishlist()["products"]
	}
	context.breadcrumb_links = [
		{"label": _("Home"), "url": url("/")},
		*(
			[
				{
					"label": product["collection"]["title"],
					"url": url(f"/products?{urlencode({'category': product['collection']['handle']})}"),
				}
			]
			if product["collection"]
			else []
		),
		{"label": product["title"]},
	]
	add_seo(context, product)
	return context


def add_seo(context, product):
	variant_fields = {
		"name": product["id"],
		"display_name": product["title"],
		"meta_title": product["seo"]["title"] if product["seo"]["custom_title"] else None,
		"meta_description": product["seo"]["description"],
		"noindex": product["seo"]["noindex"],
	}
	product_fields = {
		"item_code": product["selected_variant_id"],
		"brand": product["vendor"],
		"description": frappe.utils.strip_html(product["description_html"]),
	}
	availability = "InStock" if product["available"] else "OutOfStock"
	context.seo = seo.build_product_seo(
		variant_fields,
		product_fields,
		image_url=get_og_image_url(product["handle"]),
		price=product["price"],
		availability=availability,
		currency=product["currency"],
	)
	context.json_ld = [
		seo.build_product_json_ld(
			variant_fields,
			product_fields,
			images=product["images"],
			price=product["price"],
			availability=availability,
			currency=product["currency"],
			review_count=product["rating"]["count"],
			average_rating=product["rating"]["average"],
		),
		seo.build_breadcrumb_json_ld(
			[
				{"label": crumb["label"], "href": crumb.get("url", product_url(product["handle"]))}
				for crumb in context.breadcrumb_links
			]
		),
	]


def get_og_image_url(handle):
	"""The card shows the store price, so a secondary market shares the card without one."""
	url = seo.get_product_og_image(handle)
	market = get_localization().market
	return url if not market or market.is_primary else f"{url}?price=none"
