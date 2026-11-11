"""Section text as {language: text}, the default language being the source. Each translation's source
hash sits under the layout's SOURCE_HASHES; the editor never sees them."""

import copy
from dataclasses import dataclass

from commera.localization.languages import StorefrontLanguages
from commera.shop_themes.sections import get_section_schema, get_source, get_source_key

TRANSLATABLE_TYPES = frozenset({"text", "textarea"})
# {entry path: {setting id: {language: source hash}}}, beside "sections".
SOURCE_HASHES = "source_hashes"
# A published layout without "sections" holds only {entry path: {setting id: {language: text}}} here:
# translations of an inherited page, laid over it at read time. "" hides an inherited translation.
OVERLAY = "translations"


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
	def key(self) -> tuple[str, str]:
		return (self.path, self.id)

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


def index_text_settings(theme_dirs, layout) -> dict[tuple[str, str], TextSetting]:
	return {text.key: text for text in iter_text_settings(theme_dirs, layout)}


def find_text_setting(theme_dirs, layout, path, setting_id) -> TextSetting | None:
	return index_text_settings(theme_dirs, layout).get((path, setting_id))


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


def get_default_language() -> str:
	return StorefrontLanguages.load().default.code


def get_stored_hash(layout, text: TextSetting, language) -> str | None:
	return get_nested(layout, SOURCE_HASHES, text.path, text.id, language)


def set_stored_hash(layout, path, setting_id, language, source_hash: str | None):
	"""Set or, with None, drop one translation's source hash."""
	set_nested(layout, (SOURCE_HASHES, path, setting_id, language), source_hash)


def without_source_hashes(layout):
	if not isinstance(layout, dict) or SOURCE_HASHES not in layout:
		return layout
	return {key: value for key, value in layout.items() if key != SOURCE_HASHES}


def is_overlay(layout) -> bool:
	return isinstance(layout, dict) and "sections" not in layout


def iter_overlay(overlay):
	"""(path, setting id, language, text) of each translation an overlay holds."""
	for path, settings in ((overlay or {}).get(OVERLAY) or {}).items():
		for setting_id, texts in (settings if isinstance(settings, dict) else {}).items():
			for language, text in (texts if isinstance(texts, dict) else {}).items():
				yield path, setting_id, language, text


def set_overlay_text(overlay, path, setting_id, language, text: str | None, source_hash: str | None):
	"""Set or, with None, drop one overlay translation and its source hash."""
	set_nested(overlay, (OVERLAY, path, setting_id, language), text)
	set_stored_hash(overlay, path, setting_id, language, source_hash)


def apply_overlays(theme_dirs, base, overlays):
	"""`base` with each overlay's translations and hashes laid over it, the last overlay winning.
	`base` may be a cached layout, so it is copied first."""
	if not overlays or not isinstance(base, dict):
		return base
	layout = copy.deepcopy(base)
	texts = index_text_settings(theme_dirs, layout)
	default = get_default_language()
	for overlay in overlays:
		for path, setting_id, language, text in iter_overlay(overlay):
			setting = texts.get((path, setting_id))
			if setting and isinstance(text, str) and get_source(setting.value, default):
				setting.set(with_translation(setting.value, language, text, default))
				source_hash = get_nested(overlay, SOURCE_HASHES, path, setting_id, language)
				set_stored_hash(layout, path, setting_id, language, source_hash if text else None)
	return layout


def owner_text_settings(owner, schema, path, labels):
	for setting in schema.get("settings") or []:
		if setting.get("type") in TRANSLATABLE_TYPES and setting.get("id"):
			label = " · ".join([*labels, setting.get("label") or setting["id"]])
			yield TextSetting(path=path, owner=owner, setting=setting, label=label)


def get_nested(data, *keys):
	for key in keys:
		if not isinstance(data, dict):
			return None
		data = data.get(key)
	return data


def set_nested(data: dict, keys: tuple, value):
	"""Set data[k1][k2]...= value, or with None pop it and prune the dicts it leaves empty."""
	*parents, last = keys
	chain = [data]
	for key in parents:
		child = chain[-1].get(key)
		if not isinstance(child, dict):
			if value is None:
				return
			child = chain[-1][key] = {}
		chain.append(child)
	if value is not None:
		chain[-1][last] = value
		return
	chain[-1].pop(last, None)
	for parent, key in zip(reversed(chain[:-1]), reversed(parents), strict=True):
		if parent[key]:
			break
		parent.pop(key)
