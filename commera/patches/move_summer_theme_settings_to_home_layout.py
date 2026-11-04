import copy

import frappe
from frappe.utils.data import cint

from commera.shop_themes.doctype.shop_theme.shop_theme import build_theme_context
from commera.shop_themes.sections import (
	DEFAULT_MAX_BLOCKS,
	get_section_schema,
	get_theme_json,
	validate_layout,
)

THEME = "Summer Theme"
SETTINGS_DOCTYPE = "Summer Theme Settings"
SLIDE_FIELDS = ("image", "thumbnail_label", "heading", "subheading", "cta_label", "url")
CATEGORY_FIELDS = ("image", "heading", "url")
BANNER_FIELDS = ("image", "badge_label", "heading", "cta_label", "url")
PICKS_SECTIONS = {
	"products_grid": "best_picks",
	"everyday_essentials": "best_picks",
	"deals": "deal_picks",
	"featured": "featured_picks",
}


def execute():
	filters = {"theme": THEME, "page": "index"}
	if not frappe.db.exists("Shop Theme", THEME) or frappe.db.exists("Theme Layout", filters):
		return
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return

	settings = frappe.get_single(SETTINGS_DOCTYPE)
	overrides = get_overrides(settings)
	if not any(override["settings"] or override["blocks"] for override in overrides.values()):
		return

	theme_context = build_theme_context(THEME)
	layout = copy.deepcopy(get_theme_json(theme_context["dirs"], "layouts/index.json"))
	for section in layout["sections"]:
		if section["type"] in overrides:
			apply_override(theme_context, section, overrides[section["type"]])

	theme_layout = frappe.new_doc("Theme Layout").update(filters)
	theme_layout.draft_layout = theme_layout.published_layout = frappe.as_json(layout)
	try:
		theme_layout.insert(ignore_permissions=True)
	except frappe.ValidationError:
		frappe.log_error(title="Summer Theme Settings were not carried into the home layout")


def get_overrides(settings):
	overrides = {
		"hero_slider": get_override(
			{"caption_label": settings.hero_caption_label, "caption": settings.hero_caption},
			"slide",
			settings.hero_slides,
			SLIDE_FIELDS,
		),
		"category_strip": get_override(
			{"title": settings.categories_title, "description": settings.categories_description},
			"category",
			settings.shop_by_category,
			CATEGORY_FIELDS,
		),
		"collection": get_override({}, "banner", settings.collection_banners, BANNER_FIELDS),
		"offers": get_override(
			{"title": settings.offers_title}, "banner", settings.offer_banners, BANNER_FIELDS
		),
	}
	section_settings = {
		"products_grid": {"title": settings.products_title},
		"everyday_essentials": {},
		"deals": {
			"title": settings.deals_title,
			"link_label": settings.deals_link_label,
			"link_url": settings.deals_url,
		},
		"featured": {"title": settings.featured_title},
	}
	picked_products = get_picked_products(settings)
	for section_type, picks_field in PICKS_SECTIONS.items():
		overrides[section_type] = get_override(section_settings[section_type], None, [], ())
		if picked_products[picks_field]:
			overrides[section_type]["settings"].update(
				source="hand_picked", products=picked_products[picks_field]
			)
	return overrides


def get_override(section_settings, block_type, rows, fields):
	blocks = [
		{
			"id": f"{block_type}-{index}",
			"type": block_type,
			"settings": {field: row.get(field) for field in fields if row.get(field)},
		}
		for index, row in enumerate(rows, start=1)
	]
	return {"settings": {key: value for key, value in section_settings.items() if value}, "blocks": blocks}


def get_picked_products(settings):
	picks = {
		field: [row.item_variant for row in settings.get(field) if row.item_variant]
		for field in set(PICKS_SECTIONS.values())
	}
	codes = {code for products in picks.values() for code in products}
	published = set(
		frappe.get_all(
			"Style Attribute Variant",
			filters={"name": ("in", list(codes)), "is_published": 1},
			pluck="name",
		)
		if codes
		else []
	)
	for field, products in picks.items():
		dropped_products = [code for code in products if code not in published]
		if dropped_products:
			frappe.log_error(
				title="Summer Theme Settings picks dropped from the home layout",
				message=f"{field}: {', '.join(dropped_products)} no longer exist or are not published.",
			)
	return {field: [code for code in products if code in published] for field, products in picks.items()}


def apply_override(theme_context, section, override):
	section["settings"].update(override["settings"])
	if section["type"] in PICKS_SECTIONS:
		section["hidden"] = override["settings"].get("source") != "hand_picked"
		return

	schema = get_section_schema(theme_context["dirs"], section["type"])
	blocks = [block for block in override["blocks"] if is_valid_block(theme_context, section, block)]
	section["blocks"] = blocks[: cint(schema.get("max_blocks")) or DEFAULT_MAX_BLOCKS]
	section["hidden"] = not section["blocks"]


def is_valid_block(theme_context, section, block):
	try:
		validate_layout(theme_context, {"sections": [{**section, "settings": {}, "blocks": [block]}]})
	except frappe.ValidationError:
		frappe.log_error(
			title="Summer Theme Settings block dropped from the home layout",
			message=f"{section['id']}: {frappe.as_json(block)}",
		)
		return False
	return True
