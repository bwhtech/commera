"""Theme section text as a translatable resource. The text stays in the theme's layout JSON; an inherited
page keeps only a sparse translation overlay, so the parent theme's layout keeps applying."""

from dataclasses import dataclass

import frappe
from frappe import _

from commera.localization.content import get_source_hash, get_status
from commera.localization.resources import BATCH_SIZE, TranslatableResource, TranslationEntry
from commera.shop_themes.doctype.shop_theme.shop_theme import get_theme_context, resolve_active_theme
from commera.shop_themes.layout_cache import get_published_layouts
from commera.shop_themes.section_text import (
	OVERLAY,
	find_text_setting,
	get_default_language,
	get_nested,
	get_stored_hash,
	get_translations,
	index_text_settings,
	is_overlay,
	iter_overlay,
	iter_text_settings,
	set_overlay_text,
	set_stored_hash,
	with_translation,
)
from commera.shop_themes.sections import (
	get_inherited_layout,
	get_pages,
	get_source,
	resolve_inherited_layout,
)

THEME_LAYOUT = "Theme Layout"


@dataclass(frozen=True)
class ThemeSectionResource(TranslatableResource):
	"""Text and textarea settings of every section and block on each page of a theme, the live theme
	by default. An entry's name is "page/section id" or "page/section id/block id"; its field the setting id."""

	theme: str | None = None

	def scan(self, language, filters, after, batch_size=BATCH_SIZE):
		"""A theme has few entries, so they are sorted in memory by their key, [name, setting id]."""
		entries = sorted(self.iter_all_entries(language), key=lambda entry: (entry.name, entry.field))
		for entry in entries:
			key = [entry.name, entry.field]
			if (not after or key > after) and matches_filters(entry, filters):
				yield entry, key

	def iter_all_entries(self, language):
		theme_context = self.get_theme_context()
		if not theme_context:
			return
		default = get_default_language()
		for page in get_pages(theme_context["dirs"]):
			layout = get_inherited_layout(theme_context["names"], theme_context["dirs"], page)
			for text in iter_text_settings(theme_context["dirs"], layout):
				if source := get_source(text.value, default):
					yield self.make_entry(page, text, layout, source, language, default)

	def scan_sourceless(self, language, batch_size=BATCH_SIZE):
		"""Translations this theme stores for text without a source: in its own full layout, or
		dormant in its overlay, where the inherited text lost its source or is gone."""
		theme_context = self.get_theme_context()
		if not theme_context:
			return
		names, theme_dirs = theme_context["names"], theme_context["dirs"]
		default = get_default_language()
		for page in get_pages(theme_dirs):
			published = get_published_layouts(names, page)
			own = published[names[0]]
			if is_overlay(own):
				layout = resolve_inherited_layout(names, theme_dirs, page, published)
				yield from self.iter_dormant_entries(theme_dirs, page, own, layout, language, default)
				continue
			for text in iter_text_settings(theme_dirs, own):
				if not get_source(text.value, default) and get_translations(text.value, default).get(
					language
				):
					yield self.make_entry(page, text, own, "", language, default)

	def iter_dormant_entries(self, theme_dirs, page, overlay, layout, language, default):
		texts = index_text_settings(theme_dirs, layout)
		for path, setting_id, text_language, value in iter_overlay(overlay):
			text = texts.get((path, setting_id))
			if text_language != language or not value or (text and get_source(text.value, default)):
				continue
			yield TranslationEntry(
				resource=self.type,
				name=f"{page}/{path}",
				field=setting_id,
				label=text.label if text else setting_id,
				source="",
				value=value,
				status=get_status("", value, None),
			)

	def exists(self, name, field):
		theme_context = self.get_theme_context()
		page, _slash, path = name.partition("/")
		if not theme_context or page not in get_pages(theme_context["dirs"]):
			return False
		names, theme_dirs = theme_context["names"], theme_context["dirs"]
		published = get_published_layouts(names, page)
		layout = resolve_inherited_layout(names, theme_dirs, page, published)
		own = published[names[0]]
		in_overlay = is_overlay(own) and get_nested(own, OVERLAY, path, field) is not None
		return in_overlay or bool(find_text_setting(theme_dirs, layout, path, field))

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

	def check_write_permission(self, saving):
		frappe.has_permission(THEME_LAYOUT, "write", throw=True)

	def save_translation(self, name, field, language, value, market):
		"""Write into the live layout, or its overlay on an inherited page, and into the draft when the
		draft has that entry. Each written field is stamped current, even when its text is unchanged."""
		theme_context = self.get_theme_context()
		if not theme_context:
			frappe.throw(_("The theme has no section layouts to translate."))
		page, _slash, path = name.partition("/")
		if page not in get_pages(theme_context["dirs"]):
			throw_not_found(name, field)

		theme_layout = get_theme_layout(theme_context["theme_name"], page)
		live = parse_layout(theme_layout.published_layout)
		if live and not is_overlay(live):
			if not set_translation(theme_context["dirs"], live, path, field, language, value):
				throw_not_found(name, field)
		else:
			live = set_inherited_translation(theme_context, page, live or {}, path, field, language, value)
		draft = parse_layout(theme_layout.draft_layout)
		if draft:
			set_translation(theme_context["dirs"], draft, path, field, language, value)
		if theme_layout.is_new() and not live and not draft:
			return

		theme_layout.published_layout = frappe.as_json(live) if live else None
		theme_layout.draft_layout = frappe.as_json(draft) if draft else None
		theme_layout.save()

	def get_theme_context(self) -> dict | None:
		"""None for a Classic theme, or no theme: they have no section layouts."""
		theme_context = get_theme_context(self.theme or resolve_active_theme())
		return theme_context if theme_context["theme_type"] == "Sections" else None


def set_translation(theme_dirs, layout, path, setting_id, language, value) -> bool:
	"""Set one translation in a full layout, with a fresh source hash. False when it has no source there."""
	text = find_text_setting(theme_dirs, layout, path, setting_id)
	default = get_default_language()
	source = get_source(text.value, default) if text else ""
	if not source:
		return False
	text.set(with_translation(text.value, language, value, default))
	set_stored_hash(layout, path, setting_id, language, get_source_hash(source) if value else None)
	return True


def set_inherited_translation(theme_context, page, overlay, path, setting_id, language, value) -> dict:
	"""`overlay` with one translation of the inherited page set; None once it holds nothing."""
	parent = get_inherited_layout(theme_context["names"][1:], theme_context["dirs"], page)
	text = find_text_setting(theme_context["dirs"], parent, path, setting_id)
	default = get_default_language()
	source = get_source(text.value, default) if text else ""
	if not source:
		# A translation of a setting the parent dropped can still be cleared.
		if value or get_nested(overlay, OVERLAY, path, setting_id, language) is None:
			throw_not_found(f"{page}/{path}", setting_id)
		set_overlay_text(overlay, path, setting_id, language, None, None)
	elif value:
		set_overlay_text(overlay, path, setting_id, language, value, get_source_hash(source))
	else:
		# Removing a translation the parent ships needs an empty one to hide it.
		hidden = "" if language in get_translations(text.value, default) else None
		set_overlay_text(overlay, path, setting_id, language, hidden, None)
	return overlay if overlay.get(OVERLAY) else None


def matches_filters(entry, filters) -> bool:
	return filters.get("name") in (None, entry.name) and filters.get("field") in (None, entry.field)


def get_theme_layout(theme, page):
	if name := frappe.db.get_value(THEME_LAYOUT, {"theme": theme, "page": page}):
		return frappe.get_doc(THEME_LAYOUT, name)
	return frappe.new_doc(THEME_LAYOUT, theme=theme, page=page)


def parse_layout(value):
	return frappe.parse_json(value) if value else None


def throw_not_found(name, field):
	frappe.throw(
		_("Theme section text {0} {1} does not exist.").format(name, field), frappe.DoesNotExistError
	)
