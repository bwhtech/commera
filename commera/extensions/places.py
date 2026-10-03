import json
import re
from pathlib import Path

# The kit reads the same file, so the server and the build never disagree on the folder grammar.
GRAMMAR = json.loads((Path(__file__).parents[2] / "packages" / "extension-kit" / "places.json").read_text())
PLACES = GRAMMAR["places"]
ICONS = frozenset(json.loads((Path(__file__).parents[1] / "sdk" / "extension_icons.json").read_text()))
NAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
RECORDLESS_PLACES = frozenset(place for place, spec in PLACES.items() if not spec["doctype"])
RECORD_DOCTYPES = {place.split("/")[0]: spec["doctype"] for place, spec in PLACES.items() if spec["doctype"]}


def get_record_place_prefix(doctype: str) -> str | None:
	return next(
		(prefix for prefix, record_doctype in RECORD_DOCTYPES.items() if record_doctype == doctype), None
	)
