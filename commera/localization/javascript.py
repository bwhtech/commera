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
		for token in region_tokens(source, line)
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


def region_tokens(source, line):
	position = 0
	while position < len(source):
		for token in tokenize(source[position:], jsx=False, dotted=False, lineno=line):
			start = source.index(token.value, position)
			position = start + len(token.value)
			line = token.lineno + token.value.count("\n")
			if token.type == "template_string":
				end, expressions = template_expressions(source, start)
				value = source[start:end]
				yield token._replace(value=value)
				for expression, offset in expressions:
					yield from region_tokens(expression, token.lineno + source[start:offset].count("\n"))
				position = end
				line = token.lineno + value.count("\n")
				break
			yield token
		else:
			return


def template_expressions(source, start):
	expressions = []
	position = start + 1
	while position < len(source):
		if source[position] == "\\":
			position += 2
		elif source[position] == "`":
			return position + 1, expressions
		elif source.startswith("${", position):
			begin = position + 2
			position = interpolation_end(source, begin)
			expressions.append((source[begin:position], begin))
			position += 1
		else:
			position += 1
	return position, expressions


def interpolation_end(source, start, depth=1):
	position = start
	for token in tokenize(source[start:], jsx=False, dotted=False):
		begin = source.index(token.value, position)
		position = begin + len(token.value)
		if token.type == "template_string":
			end, _ = template_expressions(source, begin)
			# Resume lexing after nested templates, which Babel may truncate at an inner backtick.
			return interpolation_end(source, end, depth)
		if token.value == "{":
			depth += 1
		elif token.value == "}":
			depth -= 1
			if depth == 0:
				return begin
	return len(source)


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
