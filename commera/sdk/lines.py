"""Cart, checkout and order lines in the request language: the title of the product that sells each item."""

from functools import cached_property

import frappe
from frappe import _

from commera.api.admin.catalog import DEFAULT_SIZE_VALUE
from commera.localization import get_localization
from commera.sdk.catalog import translate_products, translate_term
from commera.sdk.types import CartLineProduct
from commera.search.record_builder import images_for_variants


class LineProducts:
	"""The products that sell a set of items, read once with one translate() call for all lines.
	Item codes and sizes stay in source form; only titles are translated."""

	def __init__(self, item_codes: list[str]):
		self.item_codes = list({code for code in item_codes if code})
		self.localization = get_localization()

	def get_title(self, item_code: str, item_name: str | None) -> str | None:
		"""The line title as on the product card, followed by the size, like the Item's own name."""
		if self.localization.language.code == self.localization.default_language.code:
			return item_name
		product = self.products.get(item_code)
		if not product or not product.title:
			return _(item_name, lang=self.localization.language.code) if item_name else item_name
		shown_size = [translate_term(product.size)] if product.size != DEFAULT_SIZE_VALUE else []
		return " - ".join([product.title, *shown_size])

	def get_cart_products(self) -> dict[str, CartLineProduct]:
		"""The published product, size and image that sell each item."""
		published = {code: product for code, product in self.products.items() if product.is_published}
		images = images_for_variants(list({product.name for product in published.values()}))
		return {
			code: {
				"handle": product.route,
				"title": product.title,
				"variant_title": translate_term(product.size),
				"image": images.get(product.name, {}).get("image"),
			}
			for code, product in published.items()
		}

	@cached_property
	def products(self) -> dict[str, frappe._dict]:
		"""{item_code: product}, unpublished products included so old orders keep their titles."""
		sizes = frappe.get_all(
			"Color Size Item",
			filters={"item_code": ("in", self.item_codes or [""]), "parenttype": "Style Attribute Variant"},
			fields=["item_code", "size", "parent"],
		)
		variants = read_variants([row.parent for row in sizes])
		return {
			row.item_code: frappe._dict(variants[row.parent], size=row.size)
			for row in sizes
			if row.parent in variants
		}


def read_variants(names: list[str]) -> dict[str, frappe._dict]:
	variants = frappe.get_all(
		"Style Attribute Variant",
		filters={"name": ("in", list(set(names)) or [""])},
		fields=["name", "route", "display_name", "item_style", "is_published"],
	)
	titles = translate_products(variants)
	return {
		variant.name: frappe._dict(variant, title=title["display_name"])
		for variant, title in zip(variants, titles, strict=True)
	}
