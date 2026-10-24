import frappe

from commera.shop_themes.doctype.shop_theme.shop_theme import get_theme_context
from commera.shop_themes.layouts import DEFAULT_MAX_BLOCKS, save_theme_layout
from commera.shop_themes.theme_files import get_default_layout, get_section_schemas, is_valid_setting_value

SUMMER_THEME = "Summer Theme"
SUMMER_SETTINGS_DOCTYPE = "Summer Theme Settings"
SLIDE_FIELDS = ("image", "thumbnail_label", "heading", "subheading", "cta_label", "url")
CATEGORY_FIELDS = ("image", "heading", "url")
BANNER_FIELDS = ("image", "badge_label", "heading", "cta_label", "url")
COLLAGE_IMAGES = 5


def build_summer_index_layout(settings, theme=SUMMER_THEME):
	theme_dirs = get_theme_context(theme)["dirs"]
	layout = get_default_layout(theme_dirs, "index")
	builder = SummerIndexLayout(settings, get_section_schemas(theme_dirs))
	for section in layout["sections"]:
		builder.fill_section(section)
	return layout


class SummerIndexLayout:
	def __init__(self, settings, schemas):
		self.settings = settings
		self.schemas = schemas
		self.ordered_variants = get_ordered_variants(
			row.item_variant
			for fieldname in ("best_picks", "deal_picks", "featured_picks")
			for row in settings.get(fieldname) or []
		)

	def fill_section(self, section):
		fill = getattr(self, f"fill_{section['type']}", None)
		if fill:
			fill(section)
		schema = self.schemas.get(section["type"]) or {}
		block_schemas = schema.get("blocks") or {}
		section["settings"] = get_valid_settings(schema, section.get("settings"))
		section["blocks"] = [
			{**block, "settings": get_valid_settings(block_schemas[block["type"]], block["settings"])}
			for block in section.get("blocks") or []
			if block["type"] in block_schemas
		][: schema.get("max_blocks") or DEFAULT_MAX_BLOCKS]

	def fill_hero_slider(self, section):
		self.set_settings(section, caption_label="hero_caption_label", caption="hero_caption")
		section["blocks"] = self.get_row_blocks("hero_slides", "slide", SLIDE_FIELDS)

	def fill_category_strip(self, section):
		self.set_settings(section, heading="categories_title", description="categories_description")
		section["blocks"] = self.get_row_blocks("shop_by_category", "category", CATEGORY_FIELDS)

	def fill_products_grid(self, section):
		self.set_settings(section, heading="products_title")
		section["blocks"] = self.get_pick_blocks("best_picks", "pick")

	def fill_collection(self, section):
		section["blocks"] = self.get_row_blocks("collection_banners", "banner", BANNER_FIELDS)

	def fill_everyday_essentials(self, section):
		section["blocks"] = self.get_pick_blocks("best_picks", "ee-pick")

	def fill_deals(self, section):
		self.set_settings(section, heading="deals_title", link_label="deals_link_label", link_url="deals_url")
		section["blocks"] = self.get_pick_blocks("deal_picks", "deal-pick")

	def fill_offers(self, section):
		self.set_settings(section, heading="offers_title")
		section["blocks"] = self.get_row_blocks("offer_banners", "banner", BANNER_FIELDS, id_prefix="offer")

	def fill_featured(self, section):
		self.set_settings(section, heading="featured_title")
		section["blocks"] = self.get_pick_blocks("featured_picks", "featured-pick")

	def fill_collection_collage(self, section):
		categories = (self.settings.get("shop_by_category") or [])[:COLLAGE_IMAGES]
		for position, row in enumerate(categories, start=1):
			section["settings"][f"image_{position}"] = row.get("image") or ""

	def set_settings(self, section, **fieldnames):
		for setting_id, fieldname in fieldnames.items():
			section["settings"][setting_id] = self.settings.get(fieldname) or ""

	def get_row_blocks(self, table_fieldname, block_type, fields, id_prefix=None):
		return [
			{
				"id": f"{id_prefix or block_type}-{position}",
				"type": block_type,
				"settings": {field: row.get(field) or "" for field in fields},
			}
			for position, row in enumerate(self.settings.get(table_fieldname) or [], start=1)
		]

	def get_pick_blocks(self, table_fieldname, id_prefix):
		picked = {row.item_variant for row in self.settings.get(table_fieldname) or []}
		variants = [variant for variant in self.ordered_variants if variant in picked]
		return [
			{"id": f"{id_prefix}-{position}", "type": "pick", "settings": {"product": variant}}
			for position, variant in enumerate(variants, start=1)
		]


def get_valid_settings(schema, values):
	settings_by_id = {setting.get("id"): setting for setting in schema.get("settings") or []}
	return {
		setting_id: value
		for setting_id, value in (values or {}).items()
		if setting_id in settings_by_id and is_valid_setting_value(settings_by_id[setting_id], value)
	}


def get_ordered_variants(variant_names):
	variant_names = list({name for name in variant_names if name})
	if not variant_names:
		return []
	return frappe.get_all(
		"Style Attribute Variant",
		filters={"name": ["in", variant_names]},
		order_by="name asc",
		pluck="name",
	)


def sync_summer_index_layout(settings):
	for theme in get_summer_layout_themes():
		saved = frappe.db.get_value(
			"Theme Layout",
			{"theme": theme, "template": "index"},
			["layout", "published_layout", "is_synced_from_settings"],
			as_dict=True,
		)
		if saved and not saved.is_synced_from_settings:
			continue

		layout = build_summer_index_layout(settings, theme)
		saved_layouts = saved and [frappe.parse_json(saved.layout), frappe.parse_json(saved.published_layout)]
		if saved_layouts == [layout, layout]:
			continue
		save_theme_layout(
			theme, "index", layout, publish=True, ignore_permissions=True, synced_from_settings=True
		)


def get_summer_layout_themes():
	if not frappe.db.table_exists("Theme Layout"):
		return []
	return frappe.get_all("Shop Theme", filters={"theme_settings": SUMMER_SETTINGS_DOCTYPE}, pluck="name")
