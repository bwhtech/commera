"""Translated titles for the search index: one per published language besides the default.
Every engine searches them through each record's `content`."""

import json

import frappe
from frappe.utils import create_batch
from frappe.utils.background_jobs import get_job_status
from frappe.utils.data import sha256_hash
from rq.job import JobStatus

from commera.localization.content import BATCH_SIZE, DOCTYPE, SHOP_WIDE, get_lookup_market, translate
from commera.localization.languages import Language, StorefrontLanguages
from commera.localization.resolver import Localization, get_localization

# The field the index takes its title from, on both indexed doctypes.
TITLE_FIELD = "display_name"
INDEXED_DOCTYPES = ("Style Attribute Variant", "Ecommerce Category")


def get_translated_titles(doctype: str, records: list) -> dict:
	"""{name: {language: title}} for every search language. One translation query per language and
	500 records. A title equal to the record's own adds nothing, so it is left out."""
	languages = StorefrontLanguages.load()
	titles = {record.name: {} for record in records}
	for language in get_search_languages(languages):
		localization = Localization(
			language=language,
			default_language=languages.default,
			available_languages=tuple(languages.published),
			root_prefix="",
		)
		translated = translate(records, [TITLE_FIELD], localization, doctype)
		for record, values in zip(records, translated, strict=True):
			title = values[TITLE_FIELD].value
			if title and title != record.get(TITLE_FIELD):
				titles[record.name][language.code] = title
	return titles


def get_market_titles(doctype: str, names: list) -> dict:
	"""{name: {market: text}}: the titles each market overrides, in every published language. Only
	that market's searches match them, so they stay out of the record's own `content`."""
	codes = [language.code for language in StorefrontLanguages.load().published]
	texts = {}
	for batch in create_batch([name for name in names if name], BATCH_SIZE):
		rows = frappe.get_all(
			DOCTYPE,
			filters={
				"reference_doctype": doctype,
				"reference_name": ("in", batch),
				"reference_field": TITLE_FIELD,
				"language": ("in", codes),
				"market": ("is", "set"),
				"translated_value": ("is", "set"),
			},
			fields=["reference_name", "market", "translated_value"],
			order_by="language asc",
		)
		for row in rows:
			titles = texts.setdefault(row.reference_name, {}).setdefault(row.market, [])
			if row.translated_value not in titles:
				titles.append(row.translated_value)
	return {
		name: {market: " ".join(titles) for market, titles in markets.items()}
		for name, markets in texts.items()
	}


def get_search_markets() -> list[str]:
	"""The markets whose titles a search of this request matches: shop-wide, and its own market."""
	return list(dict.fromkeys((SHOP_WIDE, get_lookup_market(get_localization().market))))


def reindex_market_records(market: str):
	"""Commera Market on_trash, before its translations go: reindex each record that held its titles."""
	from commera.search.sync import enqueue_upsert_many

	for doctype in INDEXED_DOCTYPES:
		filters = {"reference_doctype": doctype, "reference_field": TITLE_FIELD, "market": market}
		names = frappe.get_all(DOCTYPE, filters=filters, pluck="reference_name", distinct=True)
		enqueue_upsert_many(doctype, names)


def get_search_languages(languages: StorefrontLanguages | None = None) -> list[Language]:
	"""The published languages the index holds titles for. The default one is the record's own."""
	languages = languages or StorefrontLanguages.load()
	return [language for language in languages.published if language != languages.default]


def on_translation_change(doc, method=None):
	"""Content Translation on_update and on_trash: reindex each record whose search title changed."""
	from commera.search.sync import enqueue_upsert

	languages = StorefrontLanguages.load()
	codes = {language.code for language in get_search_languages(languages)}
	# A market overrides the default language too.
	market_codes = {language.code for language in languages.published}
	# An edit can move a translation to another record or language: the old record drops its title.
	records = {
		(version.reference_doctype, version.reference_name)
		for version in (doc.get_doc_before_save(), doc)
		if version and is_search_title(version, market_codes if version.market else codes)
	}
	for doctype, name in sorted(records):
		enqueue_upsert(doctype, name)


def is_search_title(translation, codes: set[str]) -> bool:
	return (
		translation.reference_doctype in INDEXED_DOCTYPES
		and translation.reference_field == TITLE_FIELD
		and translation.language in codes
	)


def search_languages_changed(before, after) -> bool:
	"""Whether a Commera Settings save changed the default or the languages the index holds titles for."""
	return before is not None and index_languages(before) != index_languages(after)


def index_languages(settings) -> tuple[str, list[str]]:
	languages = StorefrontLanguages.from_settings(settings)
	return languages.default.code, [language.code for language in get_search_languages(languages)]


def language_generation(settings=None) -> str:
	"""A hash of the languages a full build indexes. A build compares it at its start and end."""
	settings = settings or frappe.get_cached_doc("Commera Settings")
	return sha256_hash(json.dumps(index_languages(settings)))


def rebuild_if_languages_change(engine, generation: str, job_id: str):
	"""After a build commits, rebuild again if the languages changed while it ran."""
	# A settings save during the build saw its job as started, and dedupe dropped that save's rebuild.

	def check():
		# After the commit, so the build's read snapshot cannot hide a newer save.
		if language_generation(frappe.get_doc("Commera Settings")) == generation:
			return
		# Only a queued build reads the new settings. This build's own job still counts as started.
		if get_job_status(job_id) != JobStatus.QUEUED:
			engine.enqueue_full_rebuild()

	frappe.db.after_commit.add(check)
