"""The content a merchant can translate, declared by each app's `commera_hooks["translatable_resources"]`.
An entry is {"type", "doctype", "fields", "label"}, or {"type", "adapter", "label"} for other storage."""

from collections import Counter
from dataclasses import dataclass

import frappe
from frappe import _

from commera.localization.content import (
	CURRENT,
	DOCTYPE,
	MISSING,
	OUTDATED,
	SHOP_WIDE,
	fetch_translations,
	get_sources,
	get_status,
	register,
)
from commera.localization.languages import StorefrontLanguages

HOOK_KEY = "translatable_resources"


@dataclass(frozen=True)
class TranslationEntry:
	"""One translatable field of one record, in one language."""

	resource: str
	# Identifies the record within its resource, e.g. a product name or "index/hero/slide-1".
	name: str
	field: str
	label: str
	source: str
	# Empty when missing. An outdated value is still the one shown.
	value: str
	status: str


@dataclass(frozen=True)
class TranslatableResource:
	"""A kind of translatable content. Consumers list, count and write through this interface only,
	so the storage behind it (Content Translation rows, theme layout JSON) stays the adapter's business."""

	type: str
	label: str

	def list_entries(self, language: str) -> list[TranslationEntry]:
		"""Every field with source text, with its `language` translation and status."""
		check_target_language(language)
		return self.read_entries(language)

	def write(self, name: str, field: str, language: str, value: str):
		"""Save the shop-wide translation of a field, current against its source now. Empty removes it."""
		check_target_language(language)
		self.save_translation(name, field, language, value or "")

	def count_statuses(self, language: str) -> dict[str, int]:
		counts = Counter(entry.status for entry in self.list_entries(language))
		return {status: counts[status] for status in (MISSING, OUTDATED, CURRENT)}

	def read_entries(self, language: str) -> list[TranslationEntry]:
		raise NotImplementedError

	def save_translation(self, name: str, field: str, language: str, value: str):
		raise NotImplementedError


@dataclass(frozen=True)
class DoctypeResource(TranslatableResource):
	"""Fields of a doctype, translated in Content Translation rows."""

	doctype: str
	fields: tuple[str, ...]

	def read_entries(self, language):
		meta = frappe.get_meta(self.doctype)
		columns = [field for field in self.fields if meta.has_field(field)]
		records = frappe.get_all(self.doctype, fields=["name", *columns], order_by="name")
		sources = get_sources(self.doctype, records, list(self.fields))
		translations = fetch_translations(
			self.doctype, [record.name for record in records], self.fields, language
		)
		return [
			self.make_entry(meta, record.name, field, source[field], translations.get((record.name, field)))
			for record, source in zip(records, sources, strict=True)
			for field in self.fields
			if source[field]
		]

	def make_entry(self, meta, name, field, source, translation):
		value, source_hash = translation or ("", None)
		return TranslationEntry(
			resource=self.type,
			name=name,
			field=field,
			label=meta.get_label(field),
			source=source,
			value=value or "",
			status=get_status(source, value, source_hash),
		)

	def save_translation(self, name, field, language, value):
		if value:
			register(self.doctype, name, field, language, value)
			return
		key = {"reference_name": name, "reference_field": field, "language": language, "market": SHOP_WIDE}
		frappe.db.delete(DOCTYPE, {"reference_doctype": self.doctype, **key})


def get_translatable_resources() -> list[TranslatableResource]:
	entries = frappe.get_hooks("commera_hooks", {}).get(HOOK_KEY, [])
	return [load_resource(entry) for entry in entries]


def get_translatable_resource(resource_type: str) -> TranslatableResource:
	resource = next((item for item in get_translatable_resources() if item.type == resource_type), None)
	if not resource:
		frappe.throw(_("{0} is not a translatable resource.").format(resource_type), frappe.DoesNotExistError)
	return resource


def get_translatable_fields(doctype: str) -> set[str]:
	"""Every field of `doctype` that any app declares translatable."""
	return {
		field
		for resource in get_translatable_resources()
		if isinstance(resource, DoctypeResource) and resource.doctype == doctype
		for field in resource.fields
	}


def load_resource(entry: dict) -> TranslatableResource:
	label = entry.get("label") or entry.get("doctype") or entry["type"]
	if adapter := entry.get("adapter"):
		return frappe.get_attr(adapter)(type=entry["type"], label=label)
	return DoctypeResource(
		type=entry["type"], label=label, doctype=entry["doctype"], fields=tuple(entry["fields"])
	)


def check_target_language(language: str):
	"""Translations go to a configured language other than the default, which holds the source.
	Unpublished languages count, so a merchant can translate before publishing one."""
	languages = StorefrontLanguages.load()
	if language == languages.default.code:
		frappe.throw(_("{0} is the default language, so it holds the source text.").format(language))
	if not any(configured.code == language for configured in languages.configured):
		frappe.throw(_("{0} is not a storefront language.").format(language))
