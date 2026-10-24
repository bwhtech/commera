from commera.shop_themes.section_data import get_fallback_products, get_section_products


def get_context(section, page):
	if not section.blocks:
		return get_fallback_products((page.new_arrivals or [])[:4])
	return get_section_products(section)
