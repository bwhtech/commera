from commera.www.products import list as products_list

cacheable_ssr = True
ssr_query_params = frozenset(
	{
		"category",
		"subcategory",
		"sort_by",
		"page",
		"page_size",
		"brands",
		"colors",
		"sizes",
		"has_discount",
	}
)


def get_context(context):
	products_list.get_context(context)
	return context
