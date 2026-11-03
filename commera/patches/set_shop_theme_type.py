import frappe

from commera.shop_themes.doctype.shop_theme.shop_theme import clear_theme_cache

SECTIONS_THEME = "Summer Theme"


def execute():
	parents = dict(frappe.get_all("Shop Theme", fields=["name", "parent_theme"], as_list=True))
	sections_themes = {name for name in parents if is_sections_theme(name, parents)}
	frappe.db.set_value(
		"Shop Theme", {"theme_type": ("is", "not set")}, "theme_type", "Classic", update_modified=False
	)
	if sections_themes:
		frappe.db.set_value(
			"Shop Theme",
			{"name": ("in", list(sections_themes))},
			"theme_type",
			"Sections",
			update_modified=False,
		)
	clear_theme_cache()


def is_sections_theme(name, parents):
	visited = set()
	while name and name not in visited:
		if name == SECTIONS_THEME:
			return True
		visited.add(name)
		name = parents.get(name)
	return False
