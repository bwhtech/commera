"""Theme section text as a translatable resource. The text stays in the theme's layout JSON."""

import copy
from dataclasses import dataclass

import frappe
from frappe import _

from commera.localization.content import get_source_hash, get_status
from commera.localization.languages import StorefrontLanguages
from commera.localization.resources import TranslatableResource, TranslationEntry
from commera.shop_themes.doctype.shop_theme.shop_theme import get_theme_context, resolve_active_theme
from commera.shop_themes.section_text import (
	find_text_setting,
	get_stored_hash,
	get_translations,
	iter_text_settings,
	parse_layout,
	with_translation,
)
from commera.shop_themes.sections import get_inherited_layout, get_pages, get_source

THEME_LAYOUT = "Theme Layout"


@dataclass(frozen=True)
class ThemeSectionResource(TranslatableResource):
	"""Text and textarea settings of every section and block on each page of a theme, the live theme
	by default. An entry's name is "page/section id" or "page/section id/block id"; its field the setting id."""

	theme: str | None = None

	def read_entries(self, language):
		theme_context = self.get_theme_context()
		if not theme_context:
			return []
		default = StorefrontLanguages.load().default.code
		entries = []
		for page in get_pages(theme_context["dirs"]):
			layout = get_inherited_layout(theme_context["names"], theme_context["dirs"], page)
			for text in iter_text_settings(theme_context["dirs"], layout):
				if source := get_source(text.value, default):
					entries.append(self.make_entry(page, text, layout, source, language, default))
		return entries

	def make_entry(self, page, text, layout, source, language, default):
		value = get_translations(text.value, default).get(language, "")
		# Text the theme ships, or saved before hashes existed, has none: trust it.
		source_hash = get_stored_hash(layout, text, language) or get_source_hash(source)
		return TranslationEntry(
			resource=self.type,
			name=f"{page}/{text.path}",
			field=text.id,
			label=text.label,
			source=source,
			value=value,
			status=get_status(source, value, source_hash),
		)

	def save_translation(self, name, field, language, value):
		"""Write into the live layout and, when the entry is there too, the draft."""
		theme_context = self.get_theme_context()
		if not theme_context:
			frappe.throw(_("The theme has no section layouts to translate."))
		page, _slash, path = name.partition("/")
		if page not in get_pages(theme_context["dirs"]):
			throw_not_found(name, field)

		theme_layout = get_theme_layout(theme_context["theme_name"], page)
		# The inherited layout is a cached object: copy it before writing into it.
		live = parse_layout(theme_layout.published_layout) or copy.deepcopy(
			get_inherited_layout(theme_context["names"][1:], theme_context["dirs"], page)
		)
		draft = parse_layout(theme_layout.draft_layout) or copy.deepcopy(live)
		if not set_translation(theme_context["dirs"], live, path, field, language, value):
			throw_not_found(name, field)
		set_translation(theme_context["dirs"], draft, path, field, language, value)

		theme_layout.published_layout = frappe.as_json(live)
		theme_layout.draft_layout = frappe.as_json(draft)
		theme_layout.save()

	def get_theme_context(self) -> dict | None:
		"""None for a Classic theme, or no theme: they have no section layouts."""
		theme_context = get_theme_context(self.theme or resolve_active_theme())
		return theme_context if theme_context["theme_type"] == "Sections" else None


def set_translation(theme_dirs, layout, path, setting_id, language, value) -> bool:
	"""Set one translation in `layout`. False when the layout has no source text there."""
	text = find_text_setting(theme_dirs, layout, path, setting_id)
	default = StorefrontLanguages.load().default.code
	if not text or not get_source(text.value, default):
		return False
	text.set(with_translation(text.value, language, value, default))
	return True


def get_theme_layout(theme, page):
	if name := frappe.db.get_value(THEME_LAYOUT, {"theme": theme, "page": page}):
		return frappe.get_doc(THEME_LAYOUT, name)
	return frappe.new_doc(THEME_LAYOUT, theme=theme, page=page)


def throw_not_found(name, field):
	frappe.throw(
		_("Theme section text {0} {1} does not exist.").format(name, field), frappe.DoesNotExistError
	)
