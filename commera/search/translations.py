"""Translated titles for the search index: one per published language besides the default.
Every engine searches them through each record's `content`."""

from commera.localization.content import MISSING, TranslatedValue, translate
from commera.localization.languages import Language, StorefrontLanguages
from commera.localization.resolver import Localization

# The field the index takes its title from, on both indexed doctypes.
TITLE_FIELD = "display_name"
INDEXED_DOCTYPES = ("Style Attribute Variant", "Ecommerce Category")
LEGACY_TITLE_LANGUAGE = "ar"


def get_translated_titles(doctype: str, records: list, legacy_titles: dict | None = None) -> dict:
	"""{name: {language: title}} for every search language, one translation query per language and batch.
	A title equal to the record's own adds nothing, so it is left out."""
	languages = StorefrontLanguages.load()
	legacy_titles = legacy_titles or {}
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
			title = pick_title(values[TITLE_FIELD], legacy_titles.get(record.name), language.code)
			if title and title != record.get(TITLE_FIELD):
				titles[record.name][language.code] = title
	return titles


def get_search_languages(languages: StorefrontLanguages | None = None) -> list[Language]:
	"""The published languages the index holds titles for. The default one is the record's own."""
	languages = languages or StorefrontLanguages.load()
	return [language for language in languages.published if language != languages.default]


def pick_title(title: TranslatedValue, legacy_title: str | None, language: str) -> str:
	# Same rule as sdk.catalog.pick_title: the Item's Arabic name stays a fallback until #441.
	if title.status == MISSING and legacy_title and language == LEGACY_TITLE_LANGUAGE:
		return legacy_title
	return title.value


def on_translation_change(doc, method=None):
	"""Content Translation on_update and on_trash: reindex the record whose search title changed."""
	from commera.search.sync import enqueue_upsert

	if doc.reference_doctype not in INDEXED_DOCTYPES or doc.reference_field != TITLE_FIELD or doc.market:
		return
	if doc.language in {language.code for language in get_search_languages()}:
		enqueue_upsert(doc.reference_doctype, doc.reference_name)


def search_languages_changed(before, after) -> bool:
	"""Whether a Commera Settings save changed the default or the languages the index holds titles for."""
	return before is not None and index_languages(before) != index_languages(after)


def index_languages(settings) -> tuple[str, list[str]]:
	languages = StorefrontLanguages.from_settings(settings)
	return languages.default.code, [language.code for language in get_search_languages(languages)]
