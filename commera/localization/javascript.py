"""Extract static storefront translation calls using Babel's JavaScript lexer."""

import re
from html.parser import HTMLParser

from babel.messages.jslexer import tokenize, unquote_string


def extract_client_t_messages(code: str, markup: bool = False) -> list[tuple[int, str, None]]:
	if markup:
		parser = JavaScriptRegions()
		parser.feed(code)
		regions = parser.regions
	else:
		regions = [(code, 1)]
	messages = []
	for source, line in regions:
		messages.extend(extract_region(source, line))
	return messages


def extract_region(source, line):
	tokens = [
		token
		for token in tokenize(source, jsx=False, dotted=False, lineno=line)
		if token.type not in {"linecomment", "multilinecomment"}
	]
	messages = []
	for index, token in enumerate(tokens):
		if token.type != "name" or token.value != "t":
			continue
		previous = tokens[index - 1].value if index else None
		if previous == "function":
			continue
		if previous == ".":
			if index < 2 or tokens[index - 2].value != "commera":
				continue
			if index >= 3 and tokens[index - 3].value == ".":
				continue
		argument = index + 1
		# Babel emits the dot of an optional call as a separate token.
		if argument < len(tokens) and tokens[argument].value == ".":
			argument += 1
		if argument >= len(tokens) or tokens[argument].value != "(":
			continue
		text = static_argument(tokens, argument + 1)
		if text is None:
			raise ValueError(f"line {token.lineno}: translation argument must be a static literal")
		messages.append((token.lineno, text, None))
	return messages


def static_argument(tokens, index):
	parentheses = 0
	while index < len(tokens) and tokens[index].value == "(":
		parentheses += 1
		index += 1
	if index >= len(tokens):
		return None
	literal = tokens[index]
	if literal.type not in {"string", "template_string"}:
		return None
	if literal.type == "template_string" and re.search(r"(?<!\\)(?:\\\\)*\$\{", literal.value):
		return None
	index += 1
	for _ in range(parentheses):
		if index >= len(tokens) or tokens[index].value != ")":
			return None
		index += 1
	if index >= len(tokens) or tokens[index].value not in {",", ")"}:
		return None
	return unquote_string(literal.value)


class JavaScriptRegions(HTMLParser):
	"""Scan script bodies, Vue expressions and Alpine attributes independently."""

	def __init__(self):
		super().__init__(convert_charrefs=True)
		self.regions = []

	def handle_data(self, data):
		self.regions.append((data, self.getpos()[0]))

	def handle_starttag(self, tag, attrs):
		for name, value in attrs:
			if value and (name.startswith(("x-", ":", "@", "v-"))):
				start = self.get_starttag_text()
				offset = start.find(value)
				line = self.getpos()[0] + start[: max(offset, 0)].count("\n")
				self.regions.append((value, line))
