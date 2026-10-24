from commera.shop_themes.section_data import get_fallback_products, get_section_products


def get_context(section, page):
	if not section.blocks:
		return get_fallback_products(page.best_picks or [])
	return get_section_products(section)
