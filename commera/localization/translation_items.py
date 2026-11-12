"""The dashboard's Translations page over the resource registry: status counts per language, the
records of a resource with their fields, search across resources, and a batch save, all shop-wide."""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import groupby, islice

import frappe
from frappe import _
from frappe.utils import cint, cstr, strip_html

from commera.localization.content import CURRENT, OUTDATED, SHOP_WIDE, get_sources
from commera.localization.languages import StorefrontLanguages
from commera.localization.resources import (
	BATCH_SIZE,
	DoctypeResource,
	TranslatableResource,
	TranslationEntry,
	check_target_language,
	get_translatable_resource,
	get_translatable_resources,
)
from commera.localization.translation_fields import add_details, make_field
from commera.localization.translation_queries import RecordQuery

ITEMS_PER_PAGE = 50
SEARCH_RESULTS_PER_RESOURCE = 20
MAX_SAVE_BATCH = 500
# The storefront path of a record, by its doctype: (route field, path from the route).
STORE_PATHS = {
	"Style Attribute Variant": ("route", "/products/{0}"),
	"Ecommerce Category": ("route_slug", "/products?category={0}"),
	"Shop Web Page": ("route", "/page/{0}"),
}
# Resources shown on the homepage. A theme section is there when it sits on the index layout.
HOME_DOCTYPES = ("Commera Settings", "Landing Page Settings")
HOME_THEME_PAGE = "index/"


def get_overview() -> dict:
	"""Each target language with its counts per resource type."""
	languages = StorefrontLanguages.load()
	resources = get_translatable_resources()
	return {
		"source": languages.default.as_dict(),
		"languages": [
			{**language.as_dict(), "published": language in languages.published}
			for language in languages.configured
			if language != languages.default
		],
		"resources": [{"type": resource.type, "label": _(resource.label)} for resource in resources],
		"counts": {
			language.code: {resource.type: resource.count_work(language.code) for resource in resources}
			for language in languages.configured
			if language != languages.default
		},
	}


def get_items(
	language: str, resource_type: str, *, to_do: bool = False, record=None, cursor=None, records=None
) -> dict:
	"""One page of a resource's records, each with its fields. The first page also has `total` and
	`to_do`, the record counts; `record` or `records` selects records without the page filter."""
	resource = get_translatable_resource(resource_type)
	check_target_language(language)
	items = ItemList(resource, language)
	if records is not None:
		if isinstance(records, str):
			records = json.loads(records)
		if (
			not isinstance(records, list)
			or len(records) > MAX_SAVE_BATCH
			or any(not isinstance(name, str) for name in records)
		):
			frappe.throw(_("Provide at most {0} record names as text.").format(MAX_SAVE_BATCH))
		return {
			"items": [item for name in dict.fromkeys(records) for item in items.find(name)],
			"next_cursor": None,
		}
	if record:
		return {"items": items.find(cstr(record)), "next_cursor": None}
	return items.page(to_do=bool(cint(to_do)), cursor=cursor or None)


def search(language: str, text: str) -> list[dict]:
	"""Records whose source or translation holds `text`, by resource type, the first few of each."""
	check_target_language(language)
	text = cstr(text).strip()
	if not text:
		return []
	results = []
	for resource in get_translatable_resources():
		query = RecordQuery.for_resource(resource, language)
		names = (
			query.search(text, SEARCH_RESULTS_PER_RESOURCE)
			if query
			else list(islice(iter_matching_names(resource, language, text), SEARCH_RESULTS_PER_RESOURCE))
		)
		if names:
			titles = get_titles(resource, names) or resource.get_record_titles(names)
			records = [{"name": name, "title": titles.get(name) or name} for name in names]
			results.append({"resource": resource.type, "label": _(resource.label), "records": records})
	return results


def save(language: str, translations: list[dict] | str) -> int:
	"""Write each {resource, name, field, value} shop-wide, current against its source now. An empty
	value removes the translation. Answers how many were written."""
	if isinstance(translations, str):
		translations = json.loads(translations)
	if not isinstance(translations, list) or not 0 < len(translations) <= MAX_SAVE_BATCH:
		frappe.throw(_("Save between 1 and {0} translations at a time.").format(MAX_SAVE_BATCH))
	check_target_language(language)
	writes = []
	for translation in translations:
		if not isinstance(translation, dict) or not all(
			isinstance(translation.get(key), str) for key in ("resource", "name", "field", "value")
		):
			frappe.throw(_("Each translation names its resource, record, field and value as text."))
		resource = get_translatable_resource(translation["resource"])
		name, field, value = translation["name"], translation["field"], translation["value"]
		if not resource.exists(name, field):
			frappe.throw(_("The translation record or field does not exist."), frappe.DoesNotExistError)
		resource.check_write_permission(bool(value))
		writes.append((resource, name, field, value))
	frappe.db.savepoint("save_dashboard_translations")
	try:
		for resource, name, field, value in writes:
			resource.write(name, field, language, value, SHOP_WIDE)
	except Exception:
		frappe.db.rollback(save_point="save_dashboard_translations")
		raise
	return len(translations)


@dataclass
class ItemList:
	"""A resource's entries grouped into records. Entries come in key order, [record name, field], so a
	record's entries are next to each other and a page ends after a whole record."""

	resource: TranslatableResource
	language: str

	def page(self, to_do: bool, cursor: str | None) -> dict:
		if query := RecordQuery.for_resource(self.resource, self.language):
			return self.database_page(query, to_do, cursor)
		kinds = self.resource.get_field_kinds()
		page, total, to_do_count, last_key = [], 0, 0, None
		for name, entries in groupby(self.iter_entries(cursor), key=lambda entry: entry.name):
			item = make_item(self.resource, name, list(entries), kinds)
			total += 1
			to_do_count += bool(item["to_do"])
			if to_do and not item["to_do"]:
				continue
			if len(page) == ITEMS_PER_PAGE:
				if cursor:
					break
				# The first page goes on to count every record; a later page stops here.
				continue
			page.append(item)
			last_key = [name, item["fields"][-1]["field"]]
		more = len(page) == ITEMS_PER_PAGE and (to_do_count if to_do else total) > len(page)
		result = {"items": self.finish(page), "next_cursor": json.dumps(last_key) if more else None}
		if not cursor:
			result.update(total=total, to_do=to_do_count)
		return result

	def database_page(self, query, to_do, cursor):
		from commera.localization.content import fetch_translations
		from commera.localization.resources import parse_cursor

		after = parse_cursor(cursor)
		names = query.names(to_do, after[0] if after else None, ITEMS_PER_PAGE + 1)
		more = len(names) > ITEMS_PER_PAGE
		names = names[:ITEMS_PER_PAGE]
		meta = frappe.get_meta(self.resource.doctype)
		records = self.resource.read_records(meta, [["name", "in", names]], len(names)) if names else []
		sources = get_sources(self.resource.doctype, records, list(self.resource.fields))
		translations = fetch_translations(
			self.resource.doctype, names, list(self.resource.fields), self.language
		)
		kinds = self.resource.get_field_kinds()
		items = []
		for record, source in zip(records, sources, strict=True):
			entries = [
				self.resource.make_entry(meta, record.name, field, source[field], translations)
				for field in self.resource.fields
				if source[field]
			]
			items.append(make_item(self.resource, record.name, entries, kinds))
		result = {
			"items": self.finish(items),
			"next_cursor": json.dumps([names[-1], ""]) if more else None,
		}
		if not cursor:
			result.update(total=query.count(False), to_do=query.count(True))
		return result

	def find(self, name: str) -> list[dict]:
		page = self.resource.list_entries(self.language, filters={"name": name}, limit=BATCH_SIZE)
		if not page.entries and not self.resource.get_sourceless_entries(self.language, [name]):
			return []
		item = make_item(self.resource, name, page.entries, self.resource.get_field_kinds())
		return self.finish([item])

	def iter_entries(self, cursor: str | None) -> Iterator[TranslationEntry]:
		while True:
			page = self.resource.list_entries(self.language, cursor=cursor, limit=BATCH_SIZE)
			yield from page.entries
			if not page.next_cursor:
				return
			cursor = page.next_cursor

	def finish(self, items: list[dict]) -> list[dict]:
		add_details(self.resource, self.language, items)
		return self.with_urls(items)

	def with_urls(self, items: list[dict]) -> list[dict]:
		paths = get_store_paths(self.resource, [item["name"] for item in items])
		languages = StorefrontLanguages.load()
		prefix = languages.prefix(languages.find(self.language, include_unpublished=True))
		for item in items:
			path = paths.get(item["name"])
			item["url"] = (prefix + path if path != "/" else prefix or "/") if path else None
		return items


def make_item(resource: TranslatableResource, name: str, entries: list, kinds: dict) -> dict:
	fields = [make_field(entry, kinds.get(entry.field)) for entry in entries]
	to_do = [field for field in fields if field["status"] != CURRENT]
	return {
		"name": name,
		"title": get_entry_title(resource, name, entries),
		"fields": fields,
		"to_do": len(to_do),
		"outdated": any(field["status"] == OUTDATED for field in to_do),
	}


def get_entry_title(resource: TranslatableResource, name: str, entries: list) -> str:
	if not isinstance(resource, DoctypeResource):
		return name
	if frappe.get_meta(resource.doctype).issingle:
		return _(resource.label)
	title = next((entry.source for entry in entries if entry.field == resource.fields[0]), "")
	return strip_html(title).strip() or name


def get_titles(resource: TranslatableResource, names: list[str]) -> dict[str, str]:
	"""{name: title} for records a search found, read in one batch."""
	if not isinstance(resource, DoctypeResource):
		return {}
	meta = frappe.get_meta(resource.doctype)
	if meta.issingle:
		return dict.fromkeys(names, _(resource.label))
	title_field = resource.fields[0]
	records = resource.read_records(meta, [["name", "in", names]], len(names))
	sources = get_sources(resource.doctype, records, [title_field])
	return {
		record.name: strip_html(source[title_field]).strip()
		for record, source in zip(records, sources, strict=True)
	}


def iter_matching_names(resource: TranslatableResource, language: str, text: str) -> Iterator[str]:
	cursor, seen = None, set()
	while True:
		page = resource.list_entries(language, search=text, cursor=cursor, limit=BATCH_SIZE)
		for entry in page.entries:
			if entry.name not in seen:
				seen.add(entry.name)
				yield entry.name
		if not page.next_cursor:
			return
		cursor = page.next_cursor


def get_store_paths(resource: TranslatableResource, names: list[str]) -> dict[str, str]:
	"""{name: storefront path} for the records that have a page of their own."""
	if not isinstance(resource, DoctypeResource):
		return {name: "/" for name in names if name.startswith(HOME_THEME_PAGE)}
	if resource.doctype in HOME_DOCTYPES:
		return dict.fromkeys(names, "/")
	if resource.doctype not in STORE_PATHS or not names:
		return {}
	route_field, path = STORE_PATHS[resource.doctype]
	routes = frappe.get_all(
		resource.doctype, filters={"name": ("in", names)}, fields=["name", route_field], as_list=True
	)
	return {name: path.format(route) for name, route in routes if route}
