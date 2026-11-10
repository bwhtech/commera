# Copyright (c) 2025, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from commera.localization import get_localization, get_translatable_fields, translate

DOCTYPE = "Landing Page Settings"
BANNER = "Landing Page Hero Banner"


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
	"""The homepage GIFs, banner and hero banners with their links, in the request language."""
	settings = settings or frappe.get_cached_doc(DOCTYPE)
	localization = get_localization()
	fields, banner_fields = sorted(get_translatable_fields(DOCTYPE)), sorted(get_translatable_fields(BANNER))
	[values] = translate([settings], fields, localization, doctype=DOCTYPE)
	banners = translate(list(settings.hero_banner), banner_fields, localization, doctype=BANNER)
	return frappe._dict(
		{field: value.value for field, value in values.items()},
		hero_banner=[
			frappe._dict({field: value.value for field, value in banner.items()}) for banner in banners
		],
	)
