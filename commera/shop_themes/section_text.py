"""Section text as {language: text}, the default language being the source. Each translation's source
hash sits under the layout's SOURCE_HASHES; the editor never sees them and each save carries them over."""

from dataclasses import dataclass

import frappe
from frappe import _

from commera.localization.content import get_source_hash
from commera.localization.languages import StorefrontLanguages
from commera.shop_themes.sections import (
	LEGACY_SOURCE_LANGUAGE,
	get_inherited_layout,
	get_section_schema,
	get_source,
	get_source_key,
)

TRANSLATABLE_TYPES = frozenset({"text", "textarea"})
# {entry path: {setting id: {language: source hash}}}, beside "sections".
SOURCE_HASHES = "source_hashes"
LAYOUT_FIELDS = ("draft_layout", "published_layout")


@dataclass(frozen=True)
class TextSetting:
	"""A translatable setting of one section or block in a layout."""

	# The section id, or "section id/block id".
	path: str
	owner: dict
	setting: dict
	label: str

	@property
	def id(self) -> str:
		return self.setting["id"]

	@property
	def saved(self) -> bool:
		return self.id in self.saved_settings

	@property
	def value(self):
		return self.saved_settings.get(self.id, self.setting.get("default"))

	@property
	def saved_settings(self) -> dict:
		settings = self.owner.get("settings")
		return settings if isinstance(settings, dict) else {}

	def set(self, value):
		if not isinstance(self.owner.get("settings"), dict):
			self.owner["settings"] = {}
		self.owner["settings"][self.id] = value


def prepare_theme_layout(theme_layout, theme_context):
	"""Theme Layout validate: refuse unknown language keys, then stamp each translation's source hash.
	A translation keeps the hash a stored layout has for the same text; new text hashes today's source."""
	known = get_known_layouts(theme_layout, theme_context)
	default = StorefrontLanguages.load().default.code
	for fieldname in LAYOUT_FIELDS:
		if layout := parse_layout(theme_layout.get(fieldname)):
			check_language_keys(theme_context["dirs"], layout, known)
			stamp_source_hashes(theme_context["dirs"], layout, known, default)
			theme_layout.set(fieldname, frappe.as_json(layout))


def iter_text_settings(theme_dirs, layout):
	for section in (layout or {}).get("sections") or []:
		schema = isinstance(section, dict) and get_section_schema(theme_dirs, section.get("type"))
		if not schema:
			continue
		section_name = schema.get("name") or section["type"]
		yield from owner_text_settings(section, schema, section.get("id"), [section_name])
		block_schemas = schema.get("blocks") or {}
		for block in section.get("blocks") or []:
			block_schema = isinstance(block, dict) and block_schemas.get(block.get("type"))
			if block_schema:
				path = f"{section.get('id')}/{block.get('id')}"
				labels = [section_name, block_schema.get("name") or block["type"]]
				yield from owner_text_settings(block, block_schema, path, labels)


def find_text_setting(theme_dirs, layout, path, setting_id) -> TextSetting | None:
	return next(
		(
			text
			for text in iter_text_settings(theme_dirs, layout)
			if text.path == path and text.id == setting_id
		),
		None,
	)


def get_translations(value, default) -> dict[str, str]:
	"""{language: text} of a value, without its source."""
	if not isinstance(value, dict):
		return {}
	source_key = get_source_key(value, default)
	return {language: text for language, text in value.items() if language != source_key and text}


def with_translation(value, language, text, default) -> dict:
	"""`value` with `language` set to `text`, or removed when empty. The source moves to the default
	language key first, so a legacy English source is never overwritten by an English translation."""
	texts = dict(value) if isinstance(value, dict) else {}
	texts[default] = get_source(value, default)
	if text:
		texts[language] = text
	else:
		texts.pop(language, None)
	return texts


def get_stored_hash(layout, text: TextSetting, language) -> str | None:
	hashes = (layout or {}).get(SOURCE_HASHES)
	if not isinstance(hashes, dict):
		return None
	return ((hashes.get(text.path) or {}).get(text.id) or {}).get(language)


def without_source_hashes(layout):
	if not isinstance(layout, dict) or SOURCE_HASHES not in layout:
		return layout
	return {key: value for key, value in layout.items() if key != SOURCE_HASHES}


def stamp_source_hashes(theme_dirs, layout, known_layouts, default):
	known = [index_translations(theme_dirs, known_layout, default) for known_layout in known_layouts]
	hashes = {}
	for text in iter_text_settings(theme_dirs, layout):
		if not text.saved:
			continue
		source = get_source(text.value, default)
		for language, translation in get_translations(text.value, default).items():
			stored = find_stored_hash(known, (text.path, text.id, language), translation)
			hashes.setdefault(text.path, {}).setdefault(text.id, {})[language] = stored or get_source_hash(
				source
			)

	layout.pop(SOURCE_HASHES, None)
	if hashes:
		layout[SOURCE_HASHES] = hashes


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
	"""Every text key is a configured storefront language, the legacy English source key, or a key the
	theme or a stored layout already holds, so removing a language never blocks a save."""
	allowed = {language.code for language in StorefrontLanguages.load().configured}
	allowed |= {LEGACY_SOURCE_LANGUAGE, *get_language_keys(theme_dirs, known_layouts)}
	for text in iter_text_settings(theme_dirs, layout):
		default = text.setting.get("default")
		if unknown := set(get_keys(text.value)) - allowed - set(get_keys(default)):
			frappe.throw(
				_("{0}: {1} is not a storefront language.").format(text.label, ", ".join(sorted(unknown)))
			)


def get_language_keys(theme_dirs, layouts) -> set[str]:
	return {
		key
		for layout in layouts
		for text in iter_text_settings(theme_dirs, layout)
		for key in get_keys(text.value)
	}


def get_keys(value):
	return value.keys() if isinstance(value, dict) else ()


def get_known_layouts(theme_layout, theme_context) -> list[dict]:
	"""The stored draft and live layouts before this save, then the layout the theme inherits."""
	previous = theme_layout.get_doc_before_save()
	layouts = [parse_layout(previous.get(field)) for field in LAYOUT_FIELDS] if previous else []
	layouts.append(get_inherited_layout(theme_context["names"][1:], theme_context["dirs"], theme_layout.page))
	return [layout for layout in layouts if isinstance(layout, dict)]


def owner_text_settings(owner, schema, path, labels):
	for setting in schema.get("settings") or []:
		if setting.get("type") in TRANSLATABLE_TYPES and setting.get("id"):
			label = " · ".join([*labels, setting.get("label") or setting["id"]])
			yield TextSetting(path=path, owner=owner, setting=setting, label=label)


def parse_layout(value):
	return frappe.parse_json(value) if value else None
