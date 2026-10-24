# Copyright (c) 2026, hussain@buildwithhussain.com and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SummerThemeSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from frappe.website.doctype.website_slideshow_item.website_slideshow_item import WebsiteSlideshowItem

		from commera.commera_ecommerce.doctype.recommended_variant.recommended_variant import (
			RecommendedVariant,
		)
		from commera.shop_themes.doctype.summer_hero_slide.summer_hero_slide import SummerHeroSlide
		from commera.shop_themes.doctype.summer_promo_banner.summer_promo_banner import SummerPromoBanner

		best_picks: DF.Table[RecommendedVariant]
		categories_description: DF.SmallText | None
		categories_title: DF.Data | None
		collection_banners: DF.Table[SummerPromoBanner]
		deal_picks: DF.Table[RecommendedVariant]
		deals_link_label: DF.Data | None
		deals_title: DF.Data | None
		deals_url: DF.Data | None
		featured_picks: DF.Table[RecommendedVariant]
		featured_title: DF.Data | None
		hero_caption: DF.Data | None
		hero_caption_label: DF.Data | None
		hero_slides: DF.Table[SummerHeroSlide]
		offer_banners: DF.Table[SummerPromoBanner]
		offers_title: DF.Data | None
		products_title: DF.Data | None
		shop_by_category: DF.Table[WebsiteSlideshowItem]
	# end: auto-generated types

	_DOCTYPE_NAME = "Summer Theme Settings"
