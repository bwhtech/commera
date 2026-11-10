"""The record fields a merchant can translate, declared by each app's
`commera_hooks["translatable_resources"]`: a list of {"type", "doctype", "fields", "label"} dicts."""

from dataclasses import dataclass

import frappe

HOOK_KEY = "translatable_resources"


@dataclass(frozen=True)
class TranslatableResource:
	type: str
	doctype: str
	fields: tuple[str, ...]
	label: str

	@classmethod
	def from_hook(cls, entry: dict) -> "TranslatableResource":
		return cls(
			type=entry["type"],
			doctype=entry["doctype"],
			fields=tuple(entry["fields"]),
			label=entry.get("label") or entry["doctype"],
		)


def get_translatable_resources() -> list[TranslatableResource]:
	entries = frappe.get_hooks("commera_hooks", {}).get(HOOK_KEY, [])
	return [TranslatableResource.from_hook(entry) for entry in entries]


def get_translatable_fields(doctype: str) -> set[str]:
	"""Every field of `doctype` that any app declares translatable."""
	return {
		field
		for resource in get_translatable_resources()
		if resource.doctype == doctype
		for field in resource.fields
	}
