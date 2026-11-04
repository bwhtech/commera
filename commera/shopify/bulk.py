from collections.abc import Iterable, Iterator


def get_gid_type(gid: str) -> str:
	"""gid://shopify/ProductVariant/42 -> ProductVariant"""
	parts = str(gid or "").split("/")
	return parts[-2] if len(parts) >= 2 else ""


def get_numeric_id(gid: str) -> str:
	return str(gid or "").rsplit("/", 1)[-1]


def assemble_bulk_records(lines: Iterable[dict]) -> Iterator[dict]:
	"""Children land under `record["children"][<type in their ID>]`. Shopify does not promise that
	children follow their parent directly, so the whole file is read first."""
	roots = []
	records_by_id = {}
	for line in lines:
		parent_id = line.pop("__parentId", None)
		if parent_id is None:
			roots.append(line)
		else:
			parent = records_by_id.get(parent_id)
			if parent is None:
				raise ValueError(f"Bulk line {line.get('id')} came before its parent {parent_id}")
			parent.setdefault("children", {}).setdefault(get_gid_type(line.get("id")), []).append(line)
		if line.get("id"):
			records_by_id[line["id"]] = line

	yield from roots


def get_children(record: dict, *gid_types: str) -> list[dict]:
	children = record.get("children") or {}
	return [child for gid_type in gid_types for child in children.get(gid_type, [])]
