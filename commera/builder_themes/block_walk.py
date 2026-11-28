"""Walks a theme page's blocks as Builder renders them, and checks each binding against the keys in its scope."""

import json
from dataclasses import dataclass, field
from difflib import get_close_matches

import frappe

from commera.builder_themes.schema import MISSING, ROOT_KEY, list_keys, resolve

PAGE_DATA_SOURCE = "dataScript"


@dataclass
class Problem:
	message: str
	block: str | None = None
	# set when the block is inside a component, which is edited on its own
	component: str | None = None
	is_warning: bool = False


@dataclass
class Scope:
	"""What a block can bind: the page's keys, or one item's keys inside a repeater."""

	shape: dict
	# the dotted key of the list being repeated, "" at the top of the page
	path: str = ""

	def key(self, key: str) -> str:
		return f"{self.path}.{key}" if self.path else key


@dataclass
class Usage:
	"""What the page binds, gathered on the walk for the required-part checks."""

	keys: set = field(default_factory=set)
	repeated: set = field(default_factory=set)
	attributes: set = field(default_factory=set)
	by_property: dict = field(default_factory=dict)

	def add(self, prop: str, key: str) -> None:
		self.keys.add(key)
		self.by_property.setdefault(prop, set()).add(key)

	def binds(self, prop: str, key: str) -> bool:
		return key in self.by_property.get(prop, ())


class BlockWalk:
	"""Visits the blocks Builder renders: a component instance with its overrides, a repeater's first child only."""

	def __init__(self, page_type: str):
		self.page_type = page_type
		self.usage = Usage()
		self.problems: list[Problem] = []
		# the components being visited, to name them in a problem and to stop one that embeds itself
		self.open_components: list[str] = []

	def visit(self, block: dict, scope: Scope | None) -> None:
		component = block.get("extendedFromComponent")
		definition = None if component in self.open_components else get_component_block(component)
		if not definition:
			self.visit_block(block, scope)
			return
		self.open_components.append(component)
		self.visit_block(merge_instance(definition, block), scope)
		self.open_components.pop()

	def visit_block(self, block: dict, scope: Scope | None) -> None:
		self.check_bindings(block, scope)
		self.check_typed_link(block)
		children = [child for child in block.get("children") or [] if isinstance(child, dict)]
		if is_repeater(block):
			# Builder repeats the first child and drops the others
			scope, children = self.get_item_scope(block, scope), children[:1]
		for child in children:
			self.visit(child, scope)

	def check_bindings(self, block: dict, scope: Scope | None) -> None:
		for binding in get_bindings(block):
			prop = binding.get("property") or ""
			if binding.get("type") == "attribute":
				self.usage.attributes.add(prop)
			if is_page_data(binding):
				self.check_key(block, scope, binding["key"], prop)
		self.usage.attributes.update(block.get("attributes") or {}, block.get("customAttributes") or {})
		visible = get_visibility(block)
		if visible and is_page_data(visible):
			self.check_key(block, scope, visible["key"], "visible")

	def check_key(self, block: dict, scope: Scope | None, key: str, prop: str) -> None:
		shape = self.resolve(block, scope, key)
		if shape is MISSING:
			return
		self.usage.add(prop, scope.key(key))
		if prop == "visible":
			return
		if isinstance(shape, list):
			self.report(block, f"'{key}' is a list. Repeat it with a repeater, then bind its item's keys.")
		elif isinstance(shape, dict):
			self.report(block, f"'{key}' is a group of keys. Bind one of: {', '.join(list_keys(shape))}.")

	def get_item_scope(self, block: dict, scope: Scope | None) -> Scope | None:
		"""The scope of a repeater's child: the item's keys, or None when Commera does not own the list."""
		data_key = block["dataKey"]
		key = data_key["key"]
		if not is_page_data(data_key):
			# a repeater on props or component data leaves page-data keys as they were
			return scope
		shape = self.resolve(block, scope, key)
		if shape is MISSING:
			return None
		if not isinstance(shape, list):
			self.report(block, f"'{key}' is not a list, so a repeater on it shows nothing.")
			return None
		self.usage.repeated.add(scope.key(key))
		return Scope(shape[0], scope.key(key))

	def resolve(self, block: dict, scope: Scope | None, key: str):
		"""The shape at the key, or MISSING when it is unknown: a key Commera does not own, or a wrong one (reported)."""
		if not (scope and key):
			return MISSING
		shape = resolve(scope.shape, key)
		if shape is not MISSING:
			return shape
		if scope.path:
			self.report(block, self.explain_item_key(scope, key))
		elif key.split(".")[0] == ROOT_KEY:
			self.report(block, f"'{key}' is not a key of the {self.page_type} page.{suggest(scope, key)}")
		elif resolve(scope.shape[ROOT_KEY], key) is not MISSING:
			self.report(block, f"'{key}' needs the '{ROOT_KEY}.' prefix: bind '{ROOT_KEY}.{key}'.")
		return MISSING

	def explain_item_key(self, scope: Scope, key: str) -> str:
		own = ", ".join(scope.shape)
		if key.split(".")[0] == ROOT_KEY:
			return (
				f"'{key}' is inside the repeater on '{scope.path}', which reads only its item's keys ({own}). "
				"Move the block out of the repeater, or bind an item key."
			)
		return f"'{key}' is not a key of an item of '{scope.path}'.{suggest(scope, key)} Its keys: {own}."

	def check_typed_link(self, block: dict) -> None:
		href = (block.get("attributes") or {}).get("href")
		is_bound = any(binding.get("property") == "href" for binding in get_bindings(block))
		if isinstance(href, str) and href.startswith("/") and not href.startswith("//") and not is_bound:
			self.report(
				block,
				f"The link '{href}' is typed in. Bind href to a url key (commera.shop.products_url, an item's "
				"url): a typed path breaks when the store adds a language prefix.",
				is_warning=True,
			)

	def report(self, block: dict, message: str, is_warning: bool = False) -> None:
		component = self.open_components[-1] if self.open_components else None
		self.problems.append(Problem(message, block.get("blockId"), component, is_warning))


def is_repeater(block: dict) -> bool:
	return bool(
		block.get("isRepeaterBlock") and block.get("children") and (block.get("dataKey") or {}).get("key")
	)


def get_bindings(block: dict) -> list[dict]:
	"""Every binding of the block. On a block that does not repeat, Builder also reads the older `dataKey` one."""
	bindings = get_dynamic_values(block)
	data_key = block.get("dataKey") or {}
	if data_key.get("key") and not block.get("isRepeaterBlock"):
		bindings.append(data_key)
	return bindings


def get_dynamic_values(block: dict) -> list[dict]:
	"""The block's `dynamicValues` in one shape: Builder also reads a bare key there."""
	entries = [
		entry if isinstance(entry, dict) else {"key": entry, "type": "key", "property": entry}
		for entry in block.get("dynamicValues") or []
	]
	return [entry for entry in entries if entry.get("key")]


def get_visibility(block: dict) -> dict | None:
	"""The key that shows or hides the block. An older page stores it as a bare key."""
	visible = block.get("visibilityCondition")
	if isinstance(visible, str):
		visible = {"key": visible}
	return visible if visible and visible.get("key") else None


def is_page_data(binding: dict) -> bool:
	"""False for a binding to a component's props or its own data, which Commera does not own."""
	return binding.get("comesFrom", PAGE_DATA_SOURCE) == PAGE_DATA_SOURCE


def suggest(scope: Scope, key: str) -> str:
	close = get_close_matches(key, list_keys(scope.shape), n=1)
	return f" Did you mean '{close[0]}'?" if close else ""


def merge_instance(definition: dict, instance: dict) -> dict:
	"""A component's block with what the page changes on it, as Builder's extend_block merges them for the
	published page. Only the fields the checks read."""
	merged = dict(definition)
	for name in ("attributes", "customAttributes"):
		merged[name] = {**(definition.get(name) or {}), **(instance.get(name) or {})}
	overrides = get_dynamic_values(instance)
	overridden = {binding.get("property") for binding in overrides}
	merged["dynamicValues"] = overrides + [
		binding for binding in get_dynamic_values(definition) if binding.get("property") not in overridden
	]
	merged["visibilityCondition"] = instance.get("visibilityCondition") or definition.get(
		"visibilityCondition"
	)
	set_keys = {
		key: value for key, value in (instance.get("dataKey") or {}).items() if value not in (None, "")
	}
	merged["dataKey"] = {**(definition.get("dataKey") or {}), **set_keys}
	merged["children"] = merge_children(definition, instance)
	return merged


def merge_children(definition: dict, instance: dict) -> list[dict]:
	own = [child for child in definition.get("children") or [] if isinstance(child, dict)]
	placed = [child for child in instance.get("children") or [] if isinstance(child, dict)]
	if not placed:
		# the editor fills in an instance's children when it next opens the page
		return own
	by_id = {child.get("blockId"): child for child in own}
	merged = []
	for child in placed:
		match = by_id.get(child.get("blockId")) or by_id.get(child.get("referenceBlockId"))
		merged.append(merge_instance(match, child) if match else child)
	return merged


def get_component_block(component: str | None) -> dict | None:
	raw = component and frappe.db.get_value("Builder Component", component, "block")
	try:
		block = json.loads(raw) if raw else None
	except json.JSONDecodeError:
		return None
	return block if isinstance(block, dict) else None
