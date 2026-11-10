import re

# A stored pattern that starts with a language group, such as ^(?P<lang>en|ar)/products$.
# The language patch and the theme matcher must agree on this, so both use it.
LANGUAGE_GROUP_PREFIX = re.compile(r"^\^?\(\?P<lang>[^()]*\)/?")


def has_language_group(pattern: str | None) -> bool:
	"""`pattern` starts with a (?P<lang>…) group, as theme routes did under /<lang>/."""
	return drop_language_group(pattern) != (pattern or "")


def drop_language_group(pattern: str | None) -> str:
	return LANGUAGE_GROUP_PREFIX.sub("^", pattern or "", count=1)
