import frappe
from markupsafe import escape

from commera.commera_ecommerce.doctype.ecommerce_category.ecommerce_category import build_listing_href
from commera.shop_themes.section_data import get_raw_setting_value
from commera.shop_themes.section_render import get_language


def get_context(section, page):
	names_by_block = {block.id: get_raw_setting_value(block.settings.collection) for block in section.blocks}
	names = {name for name in names_by_block.values() if name}
	if not names:
		return {"collections_by_block": {}}

	item_groups = {
		row.name: row
		for row in frappe.get_all(
			"Item Group",
			filters={"name": ["in", list(names)]},
			fields=["name", "item_group_name", "custom_displayname", "image"],
		)
	}
	language = get_language()
	return {
		"collections_by_block": {
			block.id: frappe._dict(
				title=escape(item_group.custom_displayname or item_group.item_group_name),
				image=block.settings.image or escape(item_group.image or ""),
				href=build_listing_href(None, [item_group.name], language),
			)
			for block in section.blocks
			if (item_group := item_groups.get(names_by_block[block.id]))
		}
	}
