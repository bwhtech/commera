"""The fields of a record on the dashboard's Translations page, and what the page shows beside their
status: readable titles, translations whose source is now empty, and the source an outdated one had."""

from commera.localization.content import CURRENT, HTML_TAG, MISSING, OUTDATED
from commera.localization.resources import (
	HTML,
	IMAGE,
	LONG,
	TEXT,
	DoctypeResource,
	TranslatableResource,
	TranslationEntry,
)

# Longer text, or text over several lines, gets a text area.
SHORT_TEXT_LENGTH = 80


def make_field(entry: TranslationEntry, kind: str | None) -> dict:
	kind = kind or guess_kind(entry.source or entry.value)
	# An image without a translation shows the source image, so it is not missing. A translation
	# whose source is now empty has nothing left to translate.
	is_current = (kind == IMAGE and entry.status == MISSING) or not entry.source
	return {
		"field": entry.field,
		"label": entry.label,
		"kind": kind,
		"source": entry.source,
		"value": entry.value,
		"status": CURRENT if is_current else entry.status,
		"source_empty": not entry.source,
		"previous_source": None,
	}


def guess_kind(source: str) -> str:
	if HTML_TAG.search(source):
		return HTML
	return LONG if len(source) > SHORT_TEXT_LENGTH or "\n" in source else TEXT


def add_details(resource: TranslatableResource, language: str, items: list[dict]):
	if not items:
		return
	titles = resource.get_record_titles([item["name"] for item in items])
	for item in items:
		item["title"] = titles.get(item["name"]) or item["title"]
	add_sourceless_fields(resource, language, items)
	add_previous_sources(resource, language, items)


def add_sourceless_fields(resource: TranslatableResource, language: str, items: list[dict]):
	"""Shown so the merchant can see or clear them, but never counted: nothing is left to translate."""
	by_name = {item["name"]: item for item in items}
	kinds = resource.get_field_kinds()
	for entry in resource.get_sourceless_entries(language, list(by_name)):
		by_name[entry.name]["fields"].append(make_field(entry, kinds.get(entry.field)))
	if isinstance(resource, DoctypeResource):
		order = {field: index for index, field in enumerate(resource.fields)}
		for item in items:
			item["fields"].sort(key=lambda field: order.get(field["field"], len(order)))


def add_previous_sources(resource: TranslatableResource, language: str, items: list[dict]):
	outdated = [
		(item["name"], field) for item in items for field in item["fields"] if field["status"] == OUTDATED
	]
	if not outdated:
		return
	previous = resource.get_previous_sources(language, [(name, field["field"]) for name, field in outdated])
	for name, field in outdated:
		field["previous_source"] = previous.get((name, field["field"]))
