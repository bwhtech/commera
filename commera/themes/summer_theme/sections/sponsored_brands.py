import frappe

from commera.shop_themes.section_data import get_block_products


def get_context(section, page):
	stocked_brands = [
		brand
		for brand in frappe.get_all("Item", filters={"disabled": 0}, pluck="brand", distinct=True)
		if brand
	]
	if not stocked_brands:
		return {"sponsored_brands": [], "picks": []}

	pick_blocks = [
		block
		for layout_section in page.layout_sections
		for block in layout_section.blocks
		if block.type == "pick"
	]
	return {
		"sponsored_brands": frappe.get_all(
			"Brand",
			filters={"name": ["in", stocked_brands]},
			fields=["name", "image"],
			order_by="brand asc",
		),
		"picks": get_block_products(pick_blocks)[0],
	}
