# Copyright (c) 2025, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cstr

from commera.commera_ecommerce.doctype.commera_settings.editor_input import SAFE_URL_SCHEMES
from commera.localization import get_localization, get_translatable_fields, translate
from commera.localization.urls import INERT_LINK, Link

DOCTYPE = "Landing Page Settings"
LINK_FIELDS = (*(f"gif_url_{number}" for number in range(1, 5)), "banner_url_1")


class LandingPageSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from commera.commera_ecommerce.doctype.landing_page_hero_banner.landing_page_hero_banner import (
			LandingPageHeroBanner,
		)
		from commera.commera_ecommerce.doctype.recommended_variant.recommended_variant import (
			RecommendedVariant,
		)

		banner_1: DF.AttachImage | None
		banner_url_1: DF.Data | None
		best_picks: DF.Table[RecommendedVariant]
		gif_1: DF.Attach | None
		gif_2: DF.Attach | None
		gif_3: DF.Attach | None
		gif_4: DF.Attach | None
		gif_url_1: DF.Data | None
		gif_url_2: DF.Data | None
		gif_url_3: DF.Data | None
		gif_url_4: DF.Data | None
		hero_banner: DF.Table[LandingPageHeroBanner]
		new_arrivals: DF.Table[RecommendedVariant]
	# end: auto-generated types
	pass


def get_translated_landing_page(settings=None) -> frappe._dict:
	"""The homepage GIFs, banner and hero banners with their links, in the request language.
	Links are safe for an `href`: the homepage templates do not autoescape."""
	settings = settings or frappe.get_cached_doc(DOCTYPE)
	localization = get_localization()
	fields = sorted(get_translatable_fields(DOCTYPE))
	[values] = translate([settings], fields, localization, doctype=DOCTYPE)
	page = frappe._dict({field: value.value for field, value in values.items()})
	for field in LINK_FIELDS:
		if field in page:
			page[field] = get_safe_link(page[field])
	page.hero_banner = [
		frappe._dict(row.as_dict(), url=get_safe_link(row.url))
		for row in get_hero_banners(settings.hero_banner, localization.language.code)
	]
	return page


def get_hero_banners(banners: list, language: str) -> list:
	"""The banners tagged with `language`, in order. A language with none shows the untagged banners."""
	tagged = [row for row in banners if row.language == language]
	return tagged or [row for row in banners if not row.language]


def get_safe_link(value) -> str:
	"""`value` if it is a relative or http(s) link, else a link that goes nowhere."""
	value = cstr(value) or "/"
	try:
		scheme = Link(value).parts.scheme
	except ValueError:
		# urlsplit rejects some malformed hosts, such as an unclosed IPv6 bracket.
		return INERT_LINK
	return value if scheme in SAFE_URL_SCHEMES else INERT_LINK
