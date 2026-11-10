"""Theme Layout validate for section text: refuse unknown language keys, then stamp source hashes.
The draft and the live layout keep separate hashes; publishing carries the draft's over."""

import frappe
from frappe import _

from commera.localization.content import get_source_hash
from commera.localization.languages import StorefrontLanguages
from commera.shop_themes.section_text import (
	SOURCE_HASHES,
	apply_overlays,
	get_default_language,
	get_stored_hash,
	get_translations,
	index_text_settings,
	is_overlay,
	iter_overlay,
	iter_text_settings,
	set_stored_hash,
)
from commera.shop_themes.sections import LEGACY_SOURCE_LANGUAGE, get_inherited_layout, get_source


def prepare_theme_layout(theme_layout, theme_context):
	"""Each layout trusts the hashes it carries, then a stored layout's hash for the same text,
	then hashes today's source. The draft may borrow live hashes; the live layout never borrows draft ones."""
	dirs = theme_context["dirs"]
	inherited = get_inherited_layout(theme_context["names"][1:], dirs, theme_layout.page)
	previous_draft, previous_live = get_previous_layouts(theme_layout, dirs, inherited)
	default = get_default_language()
	known = {
		"draft_layout": [previous_draft, previous_live, inherited],
		"published_layout": [previous_live, inherited],
	}
	for fieldname, known_layouts in known.items():
		layout = parse_layout(theme_layout.get(fieldname))
		if not layout:
			continue
		known_layouts = [known for known in known_layouts if isinstance(known, dict)]
		if fieldname == "published_layout" and is_overlay(layout):
			check_overlay(dirs, layout, inherited, known_layouts)
		else:
			check_language_keys(dirs, layout, known_layouts)
			stamp_source_hashes(dirs, layout, known_layouts, default)
		theme_layout.set(fieldname, frappe.as_json(layout))


def get_previous_layouts(theme_layout, theme_dirs, inherited):
	"""The stored draft and live layout before this save; a live overlay comes laid over `inherited`."""
	previous = theme_layout.get_doc_before_save()
	if not previous:
		return None, None
	live = parse_layout(previous.published_layout)
	if is_overlay(live):
		live = apply_overlays(theme_dirs, inherited, [live])
	return parse_layout(previous.draft_layout), live


def stamp_source_hashes(theme_dirs, layout, known_layouts, default):
	known = [index_translations(theme_dirs, known_layout, default) for known_layout in known_layouts]
	hashes = {}
	for text in iter_text_settings(theme_dirs, layout):
		if not text.saved:
			continue
		source = get_source(text.value, default)
		for language, translation in get_translations(text.value, default).items():
			hashes[(text.path, text.id, language)] = (
				get_stored_hash(layout, text, language)
				or find_stored_hash(known, (text.path, text.id, language), translation)
				or get_source_hash(source)
			)

	layout.pop(SOURCE_HASHES, None)
	for (path, setting_id, language), source_hash in hashes.items():
		set_stored_hash(layout, path, setting_id, language, source_hash)


def index_translations(theme_dirs, layout, default) -> dict:
	"""{(path, setting id, language): (translation, stored source hash)} of a stored layout."""
	index = {}
	for text in iter_text_settings(theme_dirs, layout):
		for language, translation in get_translations(text.value, default).items():
			if stored := get_stored_hash(layout, text, language):
				index[(text.path, text.id, language)] = (translation, stored)
	return index


def find_stored_hash(known, key, translation) -> str | None:
	return next((index[key][1] for index in known if key in index and index[key][0] == translation), None)


def check_language_keys(theme_dirs, layout, known_layouts):
	"""Every text key is a configured storefront language, the legacy English source key, or a key this
	setting already holds in the theme or a stored layout, so removing a language never blocks a save."""
	allowed = get_allowed_keys()
	held = get_held_keys(theme_dirs, known_layouts)
	for text in iter_text_settings(theme_dirs, layout):
		known = allowed | held.get(text.key, set()) | set(get_keys(text.setting.get("default")))
		if unknown := set(get_keys(text.value)) - known:
			throw_unknown_keys(text.label, unknown)


def check_overlay(theme_dirs, overlay, inherited, known_layouts):
	"""An overlay holds text only, under configured languages or keys its setting already holds."""
	allowed = get_allowed_keys()
	held = get_held_keys(theme_dirs, known_layouts)
	texts = index_text_settings(theme_dirs, inherited)
	for path, setting_id, language, text in iter_overlay(overlay):
		setting = texts.get((path, setting_id))
		label = setting.label if setting else f"{path} {setting_id}"
		if not isinstance(text, str):
			frappe.throw(_("{0}: a translation must be text.").format(label))
		defaults = set(get_keys(setting.setting.get("default"))) if setting else set()
		if language not in allowed | held.get((path, setting_id), set()) | defaults:
			throw_unknown_keys(label, {language})


def get_allowed_keys() -> set[str]:
	return {language.code for language in StorefrontLanguages.load().configured} | {LEGACY_SOURCE_LANGUAGE}


def get_held_keys(theme_dirs, layouts) -> dict[tuple[str, str], set[str]]:
	held = {}
	for layout in layouts:
		for text in iter_text_settings(theme_dirs, layout):
			held.setdefault(text.key, set()).update(get_keys(text.value))
	return held


def throw_unknown_keys(label, unknown):
	frappe.throw(_("{0}: {1} is not a storefront language.").format(label, ", ".join(sorted(unknown))))


def get_keys(value):
	return value.keys() if isinstance(value, dict) else ()


def parse_layout(value):
	return frappe.parse_json(value) if value else None
