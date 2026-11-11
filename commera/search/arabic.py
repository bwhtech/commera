"""Arabic search normalisation. The SQLite tokenizer has none, so the index and the query share it."""

import re

ARABIC_PATTERN = re.compile("[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
# Tatweel, harakat and Quranic marks, and the superscript alef.
MARKS = re.compile("[ـً-ٰٟ]")
LETTER_FOLDS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي"})  # noqa: RUF001
# Longest first. The stem must keep 3 letters, so "والدة" and "بالون" stay whole.
ARTICLE_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال")
MIN_STEM_LENGTH = 3
# \w leaves out combining marks, which would split a word written with harakat.
WORD = re.compile(r"[\wً-ٰٟ]+")


def arabic_word_forms(word: str) -> list[str]:
	"""The forms the index holds for `word`: folded, then folded without a leading article.
	A word that is not Arabic is its only form."""
	if not is_arabic_query(word):
		return [word]
	folded = MARKS.sub("", word).translate(LETTER_FOLDS)
	stem = strip_article(folded)
	# Both forms stay: a false article ("فالنتين") or a folded alef ("العاب") needs the full word.
	return [folded] if stem == folded else [folded, stem]


def arabic_search_forms(text: str) -> str:
	"""The forms of the Arabic words of `text` that differ from the written ones, for the index."""
	forms = {}
	for word in WORD.findall(text or ""):
		for form in arabic_word_forms(word):
			if form != word:
				forms[form] = None
	return " ".join(forms)


def strip_article(word: str) -> str:
	for prefix in ARTICLE_PREFIXES:
		if word.startswith(prefix) and len(word) - len(prefix) >= MIN_STEM_LENGTH:
			return word[len(prefix) :]
	return word


def is_arabic_query(text: str | None) -> bool:
	"""True if the text carries any Arabic-script character."""
	return bool(ARABIC_PATTERN.search(text or ""))
