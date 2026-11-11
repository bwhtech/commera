"""Finds the UI strings of the starter theme, the SDK, the storefront package and the dashboard
that Commera's translation file for a language does not translate, or translates with broken markup."""

import os
import re
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from string import Formatter

from frappe.gettext.extractors.utils import extract_messages_from_code
from frappe.translate import (
	extract_messages_from_javascript_code,
	extract_messages_from_python_code,
	read_csv_file,
)

import commera
from commera.localization.javascript import extract_client_t_messages

APP_ROOT = Path(commera.__file__).resolve().parent.parent
TRANSLATIONS_DIR = APP_ROOT / "commera" / "translations"

# Paths are relative to the app root. The starter theme also renders the shared language switcher.
SOURCES = (
	"commera/themes/commera_starter",
	"commera/templates/macros/language_switcher.html",
	"commera/sdk",
	"packages/storefront",
	"packages/plugin-kit",
	"dashboard/src",
)
SKIPPED_DIRS = {"node_modules", "test", "tests", "dist", "__pycache__"}
EXTENSIONS = (".py", ".js", ".vue", ".html")

PLACEHOLDER_PATTERN = re.compile(r"%(?:\(\w+\))?[sd]|</?[a-zA-Z][\w-]*")


@dataclass(frozen=True)
class Message:
	text: str
	context: str | None
	path: str
	line: int

	@property
	def key(self) -> str:
		return f"{self.text}:{self.context}" if self.context else self.text


@dataclass(frozen=True)
class Problem:
	message: Message
	reason: str

	def __str__(self) -> str:
		return f"{self.message.path}:{self.message.line}: {self.reason}: {self.message.key!r}"


def check_translations(lang: str) -> list[Problem]:
	"""Every UI string with no translation in `lang`, or whose translation drops or adds markup."""
	translations = get_app_translations(lang)
	problems = []
	for message in get_messages():
		translation = translations.get(message.key)
		if not translation:
			problems.append(Problem(message, "untranslated"))
		elif not markup_matches(message.text, translation):
			problems.append(Problem(message, "placeholders or tags differ"))
	return problems


def get_messages() -> list[Message]:
	"""The translatable strings of the checked sources, one per key, at their first location."""
	messages = {}
	for path in get_source_files():
		for message in extract_messages(path):
			messages.setdefault(message.key, message)
	return list(messages.values())


def get_app_translations(lang: str) -> dict[str, str]:
	"""Commera's own translation file, keyed as Frappe keys it: `text` or `text:context`."""
	path = TRANSLATIONS_DIR / f"{lang}.csv"
	if not path.exists():
		return {}
	translations = {}
	for row in read_csv_file(path):
		if len(row) < 2:
			continue
		text, translation = row[0].replace("\\n", "\n"), row[1].replace("\\n", "\n").strip()
		context = row[2] if len(row) > 2 else None
		translations[f"{text}:{context}" if context else text] = translation
	return translations


def get_source_files() -> list[Path]:
	files = []
	for source in SOURCES:
		path = APP_ROOT / source
		if path.is_file():
			files.append(path)
			continue
		for base, dirs, names in os.walk(path):
			dirs[:] = sorted(name for name in dirs if name not in SKIPPED_DIRS)
			files.extend(Path(base, name) for name in sorted(names) if name.endswith(EXTENSIONS))
	return files


def extract_messages(path: Path) -> list[Message]:
	"""Frappe's own extractors, as `bench get-untranslated` runs them, plus `t()` calls."""
	code = path.read_text(encoding="utf-8")
	if path.suffix == ".py":
		found = extract_messages_from_python_code(code)
	else:
		found = [tuple(row) for row in extract_messages_from_code(code)]
		try:
			found += extract_client_t_messages(code, markup=path.suffix != ".js")
		except ValueError as error:
			raise ValueError(f"{path}: {error}") from error
	if path.suffix == ".js":
		found += extract_messages_from_javascript_code(code)
	shown_path = str(path.relative_to(APP_ROOT) if path.is_relative_to(APP_ROOT) else path)
	return [Message(text, context, shown_path, line) for line, text, context in found]


def markup_matches(source: str, translation: str) -> bool:
	try:
		return get_markup(source) == get_markup(translation)
	except ValueError:
		return False


def get_markup(text: str) -> Counter:
	parser = TranslationHTMLParser()
	parser.feed(text)
	if parser.stack:
		raise ValueError("unclosed HTML tag")
	markup = Counter(PLACEHOLDER_PATTERN.findall(text))
	for _, field, spec, conversion in Formatter().parse(text):
		if field is not None:
			markup[(field, spec, conversion)] += 1
			markup.update(get_markup(spec))
	return markup


class TranslationHTMLParser(HTMLParser):
	VOID_TAGS = frozenset(
		{
			"area",
			"base",
			"br",
			"col",
			"embed",
			"hr",
			"img",
			"input",
			"link",
			"meta",
			"param",
			"source",
			"track",
			"wbr",
		}
	)

	def __init__(self):
		super().__init__()
		self.stack = []

	def handle_starttag(self, tag, attrs):
		if tag not in self.VOID_TAGS:
			self.stack.append(tag)

	def handle_startendtag(self, tag, attrs):
		pass

	def handle_endtag(self, tag):
		if not self.stack or self.stack.pop() != tag:
			raise ValueError("mis-nested HTML tags")
