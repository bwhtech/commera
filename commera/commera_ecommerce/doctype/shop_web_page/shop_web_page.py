# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cstr
from frappe.website.utils import cleanup_page_name

from commera.localization import MISSING, TranslatedValue, get_localization, translate

DOCTYPE = "Shop Web Page"
TRANSLATABLE_FIELDS = ("title", "content", "meta_title", "meta_description")


class ShopWebPage(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		content: DF.TextEditor
		content_ar: DF.TextEditor | None
		meta_description: DF.SmallText | None
		meta_title: DF.Data | None
		noindex: DF.Check
		og_image: DF.AttachImage | None
		published: DF.Check
		route: DF.Data | None
	# end: auto-generated types

	@staticmethod
	def get_translation_sources(field: str, names: list[str]) -> dict[str, str]:
		"""A page's title is its name, so a title translation translates the name."""
		return {name: name for name in names} if field == "title" else {}

	def before_save(self):
		if not self.route:
			# cleanup_page_name yields underscores for spaces; storefront slugs are hyphenated.
			self.route = cleanup_page_name(cstr(self.name)).replace("_", "-")

		if frappe.db.exists("Shop Web Page", {"route": self.route, "name": ("!=", self.name)}):
			frappe.throw(frappe._("Another page already uses the route {0}.").format(self.route))


def get_page_by_route(route):
	"""The page a visitor may see on this route, or None. No role holds `read`, so a shopper can never
	list drafts through frappe.client; this reads past permissions and `published` is the whole gate."""
	if not route:
		return None

	name = frappe.db.get_value("Shop Web Page", {"route": route}, "name")
	if not name:
		return None

	page = frappe.get_cached_doc("Shop Web Page", name)
	if not page.published and not frappe.has_permission("Shop Web Page", "write", doc=page):
		return None

	return page


def get_translated_page(page) -> dict[str, TranslatedValue]:
	"""The page's title, content and SEO fields in the request language."""
	localization = get_localization()
	values = translate_pages([page], TRANSLATABLE_FIELDS, localization)[0]
	if uses_legacy_content(page, values["content"], localization):
		values["content"] = TranslatedValue(page.content_ar, MISSING)
	return values


def translate_pages(
	pages: list, fields: tuple[str, ...], localization=None
) -> list[dict[str, TranslatedValue]]:
	"""Each page's `fields` in the request language, in one query."""
	records = [
		{field: page.get(field) for field in fields} | {"name": page.name, "title": page.name}
		for page in pages
	]
	return translate(records, list(fields), localization, doctype=DOCTYPE)


def uses_legacy_content(page, content: TranslatedValue, localization) -> bool:
	# `content_ar` fills in for a missing Arabic translation until #442 moves it into Content Translation.
	translated = (
		content.status != MISSING and localization.language.code != localization.default_language.code
	)
	return frappe.local.lang == "ar" and bool(page.content_ar) and not translated
