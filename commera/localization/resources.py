"""Content a merchant translates, declared in each app's `commera_hooks["translatable_resources"]` as
{"type", "doctype", "fields", "label"}, or {"type", "adapter", "label"} for other storage."""

import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, replace
from itertools import islice
from typing import ClassVar

import frappe
from frappe import _
from frappe.utils import cint, create_batch, cstr

from commera.localization.content import (
	CURRENT,
	DOCTYPE,
	MISSING,
	OUTDATED,
	SHOP_WIDE,
	count_column_statuses,
	fetch_translations,
	get_sources,
	get_status,
	register,
)
from commera.localization.languages import StorefrontLanguages

HOOK_KEY = "translatable_resources"
PAGE_SIZE = 50
BATCH_SIZE = 500
STATUSES = (MISSING, OUTDATED, CURRENT)
ENTRY_FILTERS = ("name", "field")


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
	market: str = SHOP_WIDE


@dataclass(frozen=True)
class EntryPage:
	entries: list[TranslationEntry]
	# The key of the last entry: pass it back as `cursor` for the next page. None on the last page.
	next_cursor: str | None


@dataclass(frozen=True)
class TranslatableResource:
	"""A kind of translatable content. Consumers read and write through this interface only,
	so the storage behind it (Content Translation rows, theme layout JSON) stays the adapter's business."""

	type: str
	label: str
	# Whether translations can also be scoped to one market.
	has_markets: ClassVar[bool] = False

	def list_entries(
		self,
		language: str,
		*,
		filters: dict | None = None,
		search: str | None = None,
		status: str | None = None,
		cursor: str | None = None,
		limit: int = PAGE_SIZE,
	) -> EntryPage:
		"""One page of entries with source text, in key order. `filters` takes "name" and "field"; `search`
		matches the source or the translation, any case."""
		check_target_language(language)
		check_entry_filters(filters, status)
		limit = min(max(cint(limit), 1), BATCH_SIZE)
		matches = (
			(entry, key)
			for entry, key in self.scan(language, filters or {}, parse_cursor(cursor))
			if matches_entry(entry, search, status)
		)
		page = list(islice(matches, limit + 1))
		# The next page starts after the last key returned. An entry added or removed meanwhile may show
		# or not, but no entry not yet returned is skipped, and none repeats.
		next_cursor = json.dumps(page[limit - 1][1]) if len(page) > limit else None
		return EntryPage([entry for entry, _key in page[:limit]], next_cursor)

	def iter_entries(
		self,
		language: str,
		batch_size: int = BATCH_SIZE,
		*,
		include_sourceless: bool = False,
		market_overrides: bool = False,
	) -> Iterator[TranslationEntry]:
		"""Every entry with source text, read `batch_size` records at a time, for an export. With
		`include_sourceless`, then each one whose source is now empty but holds a translation."""
		check_target_language(language, market_override=market_overrides and self.has_markets)
		for entry, _key in self.scan(language, {}, None, batch_size):
			yield entry
		if include_sourceless:
			yield from self.scan_sourceless(language, batch_size)

	def count_statuses(self, language: str) -> dict[str, int]:
		check_target_language(language)
		counts = self.aggregate_statuses(language)
		return {status: counts[status] for status in STATUSES}

	def get_market_entries(self, entries: list[TranslationEntry], language: str) -> dict:
		"""{(name, field): [its entry per market, by market]} for a batch of shop-wide entries."""
		return {}

	def write(self, name: str, field: str, language: str, value: str, market: str = SHOP_WIDE):
		"""Save the translation of a field, shop-wide or for `market`, current against its source now.
		Empty removes it. The caller needs write permission on the storage."""
		check_target_language(language, market_override=bool(market))
		if market and not self.has_markets:
			frappe.throw(_("{0} cannot be translated per market.").format(self.label))
		self.check_write_permission(bool(value))
		self.save_translation(name, field, language, value or "", market)

	def exists(self, name: str, field: str) -> bool:
		"""Whether `name` has the translatable `field`, with source text or not."""
		raise NotImplementedError

	def scan(self, language, filters, after: list | None, batch_size=BATCH_SIZE) -> Iterator[tuple]:
		"""(entry, its key as a list) in ascending key order, only keys strictly after `after`."""
		raise NotImplementedError

	def scan_sourceless(self, language, batch_size=BATCH_SIZE) -> Iterator[TranslationEntry]:
		"""Shop-wide entries without source text that hold a translation, shop-wide or for a market.
		The shop-wide value is empty when only markets hold one."""
		return iter(())

	def aggregate_statuses(self, language) -> Counter:
		return Counter(entry.status for entry, _key in self.scan(language, {}, None))

	def check_write_permission(self, saving: bool):
		raise NotImplementedError

	def save_translation(self, name: str, field: str, language: str, value: str, market: str):
		raise NotImplementedError


@dataclass(frozen=True)
class DoctypeResource(TranslatableResource):
	"""Fields of a doctype, translated in Content Translation rows, read one batch of records at a time.
	An entry's key is [record name, field]: by name, then by the field's place in the hook entry."""

	doctype: str
	fields: tuple[str, ...]
	has_markets: ClassVar[bool] = True

	def scan(self, language, filters, after, batch_size=BATCH_SIZE):
		meta = frappe.get_meta(self.doctype)
		fields = [field for field in self.fields if filters.get("field") in (None, field)]
		after_name, after_field = after or (None, None)
		for records in self.iter_record_batches(meta, filters.get("name"), after_name, batch_size):
			sources = get_sources(self.doctype, records, fields)
			names = [record.name for record in records]
			translations = fetch_translations(self.doctype, names, fields, language)
			for record, source in zip(records, sources, strict=True):
				for field in fields:
					if record.name == after_name and not self.is_field_after(field, after_field):
						continue
					if source[field]:
						entry = self.make_entry(meta, record.name, field, source[field], translations)
						yield entry, [record.name, field]

	def scan_sourceless(self, language, batch_size=BATCH_SIZE):
		meta = frappe.get_meta(self.doctype)
		translated = self.get_translated_fields(language)
		for names in create_batch(sorted(translated), batch_size):
			records = self.read_records(meta, [["name", "in", names]], batch_size)
			sources = get_sources(self.doctype, records, list(self.fields))
			translations = fetch_translations(self.doctype, names, list(self.fields), language)
			for record, source in zip(records, sources, strict=True):
				for field in self.fields:
					if field in translated[cstr(record.name)] and not source[field]:
						yield self.make_entry(meta, record.name, field, "", translations)

	def get_translated_fields(self, language) -> dict[str, set[str]]:
		"""{record name: its fields with a translation in `language`, shop-wide or for a market}."""
		rows = frappe.get_all(
			DOCTYPE,
			filters={
				"reference_doctype": self.doctype,
				"reference_field": ("in", self.fields),
				"language": language,
				"translated_value": ("is", "set"),
			},
			fields=["reference_name", "reference_field"],
			distinct=True,
			as_list=True,
		)
		translated = {}
		for name, field in rows:
			translated.setdefault(name, set()).add(field)
		return translated

	def exists(self, name, field):
		if field not in self.fields:
			return False
		if frappe.get_meta(self.doctype).issingle:
			return name == self.doctype
		return bool(frappe.db.exists(self.doctype, name))

	def is_field_after(self, field, after_field) -> bool:
		"""A cursor field no longer declared resumes at the record's first field: nothing is skipped."""
		position = self.fields.index(after_field) if after_field in self.fields else -1
		return self.fields.index(field) > position

	def iter_record_batches(self, meta, name, after_name, batch_size):
		conditions = [["name", "=", name]] if name else []
		# The cursor record may still have fields after the cursor field.
		after = ["name", ">=", after_name] if after_name else None
		while True:
			records = self.read_records(meta, conditions + ([after] if after else []), batch_size)
			if records:
				yield records
			if len(records) < batch_size:
				return
			after = ["name", ">", records[-1].name]

	def read_records(self, meta, filters, limit) -> list:
		"""Up to `limit` records by name, with their column fields. `filters` are [["name", op, value]]."""
		columns = [field for field in self.fields if meta.has_field(field)]
		if meta.issingle:
			return self.read_single(columns, filters)
		return frappe.get_all(
			self.doctype, filters=filters, fields=["name", *columns], order_by="name asc", limit=limit
		)

	def read_single(self, columns, filters) -> list:
		"""A Single has no rows: its one record is named after the doctype."""
		if not all(matches_name(self.doctype, operator, value) for _name, operator, value in filters):
			return []
		doc = frappe.get_single(self.doctype)
		return [frappe._dict(name=self.doctype, **{column: doc.get(column) for column in columns})]

	def make_entry(self, meta, name, field, source, translations):
		value, source_hash = translations.get((name, field)) or ("", None)
		return TranslationEntry(
			resource=self.type,
			name=name,
			field=field,
			label=meta.get_label(field),
			source=source,
			value=value or "",
			status=get_status(source, value, source_hash),
		)

	def aggregate_statuses(self, language):
		meta = frappe.get_meta(self.doctype)
		if meta.issingle:
			# A Single has no table to aggregate in SQL; it has one record to scan.
			return super().aggregate_statuses(language)
		counts = Counter()
		for field in self.fields:
			if meta.has_field(field):
				counts.update(count_column_statuses(self.doctype, field, language))
			else:
				counts.update(self.count_derived_statuses(meta, field, language))
		return counts

	def count_derived_statuses(self, meta, field, language) -> Counter:
		"""A field without a column has its source in Python, so count it a batch at a time."""
		counts = Counter()
		for records in self.iter_record_batches(meta, None, None, BATCH_SIZE):
			sources = get_sources(self.doctype, records, [field])
			names = [record.name for record in records]
			translations = fetch_translations(self.doctype, names, [field], language)
			for record, source in zip(records, sources, strict=True):
				if source[field]:
					value, source_hash = translations.get((record.name, field)) or ("", None)
					counts[get_status(source[field], value, source_hash)] += 1
		return counts

	def get_market_entries(self, entries, language):
		by_key = {(entry.name, entry.field): entry for entry in entries}
		rows = frappe.get_all(
			DOCTYPE,
			filters={
				"reference_doctype": self.doctype,
				"reference_name": ("in", list({entry.name for entry in entries})),
				"reference_field": ("in", self.fields),
				"language": language,
				"market": ("is", "set"),
			},
			fields=["reference_name", "reference_field", "market", "translated_value", "source_hash"],
			order_by="market asc",
		)
		markets = {}
		for row in rows:
			if entry := by_key.get((row.reference_name, row.reference_field)):
				value = row.translated_value or ""
				status = get_status(entry.source, value, row.source_hash)
				market_entry = replace(entry, market=row.market, value=value, status=status)
				markets.setdefault((entry.name, entry.field), []).append(market_entry)
		return markets

	def check_write_permission(self, saving):
		frappe.has_permission(DOCTYPE, "write" if saving else "delete", throw=True)

	def save_translation(self, name, field, language, value, market):
		if not self.exists(name, field):
			frappe.throw(
				_("{0} {1} has no translatable field {2}.").format(_(self.doctype), name, field),
				frappe.DoesNotExistError,
			)
		if value:
			register(self.doctype, name, field, language, value, market)
			return
		key = {"reference_name": name, "reference_field": field, "language": language, "market": market}
		if existing := frappe.db.get_value(DOCTYPE, {"reference_doctype": self.doctype, **key}):
			frappe.delete_doc(DOCTYPE, existing)


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


def check_target_language(language: str, *, market_override: bool = False):
	"""Translations go to a configured language other than the default, which holds the source;
	only a market may override the default. Unpublished languages count, to translate before publishing."""
	languages = StorefrontLanguages.load()
	if language == languages.default.code and not market_override:
		frappe.throw(_("{0} is the default language, so it holds the source text.").format(language))
	if not any(configured.code == language for configured in languages.configured):
		frappe.throw(_("{0} is not a storefront language.").format(language))


def check_entry_filters(filters, status):
	if unknown := set(filters or {}) - set(ENTRY_FILTERS):
		frappe.throw(_("Translations cannot be filtered by {0}.").format(", ".join(sorted(unknown))))
	if status and status not in STATUSES:
		frappe.throw(_("{0} is not a translation status.").format(status))


def matches_entry(entry: TranslationEntry, search: str | None, status: str | None) -> bool:
	if status and entry.status != status:
		return False
	needle = (search or "").strip().casefold()
	return not needle or needle in entry.source.casefold() or needle in entry.value.casefold()


def matches_name(name: str, operator: str, value) -> bool:
	if operator == "=":
		return name == value
	if operator == "in":
		return name in value
	if operator == ">=":
		return name >= value
	if operator == ">":
		return name > value
	raise ValueError(f"Unsupported name filter {operator}")


def parse_cursor(cursor: str | None) -> list | None:
	"""None or "" is the first page. Anything but the JSON key a page returned is refused."""
	if cursor is None or cursor == "":
		return None
	try:
		key = json.loads(cursor) if isinstance(cursor, str) else None
	except ValueError:
		key = None
	if not (isinstance(key, list) and len(key) == 2 and all(isinstance(part, str) for part in key)):
		frappe.throw(_("The page cursor is not valid. Load the first page again."))
	return key
