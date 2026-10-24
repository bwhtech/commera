from frappe.utils.data import cint

from commera.commera_ecommerce.doctype.ecommerce_category.ecommerce_category import build_listing_href
from commera.shop_data import get_item_groups_with_descendants
from commera.shop_themes.section_data import get_raw_setting_value
from commera.shop_themes.section_render import get_language
from commera.utils import get_product_list


def get_context(section, page):
	language = get_language()
	collection = get_raw_setting_value(section.settings.collection)
	if not collection:
		return {
			"products": get_product_list(page_length=cint(section.settings.products_to_show)),
			"view_all_href": f"/{language}/products",
		}

	item_groups = get_item_groups_with_descendants([collection])
	return {
		"products": get_product_list(
			filters={"category_item_groups": item_groups}, page_length=cint(section.settings.products_to_show)
		),
		"view_all_href": build_listing_href(None, item_groups, language),
	}
