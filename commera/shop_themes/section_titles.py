"""Readable names of theme section entries: the page, then the section and block names from the theme's
schemas, in the admin's language. "index/hero/slide-2" reads "Home, Hero, Slide 2" with a chevron between."""

from collections import Counter
from functools import partial

import frappe
from frappe import _

from commera.shop_themes.sections import get_section_schema

# A single right-pointing angle quote, which mirrors in a right-to-left language.
SEPARATOR = " \u203a "


def get_entry_titles(theme_dirs, page: str, layout) -> dict[str, str]:
	"""{entry name: title} for each section and block of a page's layout."""
	page_label = get_page_label(page)
	titles = {}
	sections = (layout or {}).get("sections") or []
	for section, schema, section_label in iter_labels(sections, partial(get_section_schema, theme_dirs)):
		section_name = f"{page}/{section.get('id')}"
		titles[section_name] = SEPARATOR.join([page_label, section_label])
		blocks = section.get("blocks") or []
		for block, _schema, block_label in iter_labels(blocks, partial(get_block_schema, schema)):
			titles[f"{section_name}/{block.get('id')}"] = SEPARATOR.join(
				[page_label, section_label, block_label]
			)
	return titles


def get_page_label(page: str) -> str:
	labels = {"index": _("Home"), "header_group": _("Header"), "footer_group": _("Footer")}
	return labels.get(page) or _(frappe.unscrub(page))


def iter_labels(owners: list, get_schema):
	"""(owner, schema, label) for each section or block with a schema. A type used more than once is
	numbered, so two slides read "Slide 1" and "Slide 2"."""
	typed = [
		(owner, schema)
		for owner in owners
		if isinstance(owner, dict) and isinstance(schema := get_schema(owner.get("type")), dict)
	]
	totals = Counter(owner["type"] for owner, _schema in typed)
	seen = Counter()
	for owner, schema in typed:
		kind = owner["type"]
		seen[kind] += 1
		label = _(schema.get("name") or frappe.unscrub(kind))
		yield owner, schema, f"{label} {seen[kind]}" if totals[kind] > 1 else label


def get_block_schema(section_schema: dict, kind):
	block_schemas = section_schema.get("blocks")
	return block_schemas.get(kind) if isinstance(block_schemas, dict) and isinstance(kind, str) else None
