"""Arabic search normalisation. The SQLite tokenizer has none, so the index and the query share it."""

import re

ARABIC_PATTERN = re.compile("[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
# Tatweel, harakat and Quranic marks, and the superscript alef.
MARKS = re.compile("[\u0640\u064b-\u065f\u0670]")
LETTER_FOLDS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي"})  # noqa: RUF001
# Longest first. The stem must keep 3 letters, so "والدة" and "بالون" stay whole.
ARTICLE_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال")
MIN_STEM_LENGTH = 3
# \w leaves out combining marks, which would split a word written with harakat.
WORD = re.compile(r"[\w\u064b-\u065f\u0670]+")


def normalize_arabic_word(word: str) -> str:
	"""`word` without marks or a leading article, with alef, ta marbuta and alef maqsura folded."""
	if not is_arabic_query(word):
		return word
	word = MARKS.sub("", word)
	return strip_article(word).translate(LETTER_FOLDS)


def arabic_search_forms(text: str) -> str:
	"""The normalised Arabic words of `text` that differ from the written ones, for the index to hold too."""
	forms = {}
	for word in WORD.findall(text or ""):
		normalized = normalize_arabic_word(word)
		if normalized != word:
			forms[normalized] = None
	return " ".join(forms)


def strip_article(word: str) -> str:
	for prefix in ARTICLE_PREFIXES:
		if word.startswith(prefix) and len(word) - len(prefix) >= MIN_STEM_LENGTH:
			return word[len(prefix) :]
	return word


def is_arabic_query(text: str | None) -> bool:
	"""True if the text carries any Arabic-script character."""
	return bool(ARABIC_PATTERN.search(text or ""))
