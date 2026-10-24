from commera.shop_themes.section_data import get_section_products


def get_context(section, page):
	return get_section_products(section)
