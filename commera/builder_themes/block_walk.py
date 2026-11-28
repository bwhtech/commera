"""Walks a theme page's blocks as Builder renders them, and checks each binding against the keys in its scope."""

import json
from dataclasses import dataclass, field
from difflib import get_close_matches

import frappe

from commera.builder_themes.schema import MISSING, ROOT_KEY, list_keys, resolve

PAGE_DATA_SOURCE = "dataScript"
# Builder keeps a component's older versions here, and an instance can stay on one.
VERSION_DOCTYPE = "Builder Snapshot"


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

	# keys shown as text or set on an attribute
	keys: set = field(default_factory=set)
	repeated: set = field(default_factory=set)
	attributes: set = field(default_factory=set)
	by_attribute: dict = field(default_factory=dict)
	# keys a link goes to
	links: set = field(default_factory=set)

	def add(self, block: dict, binding: dict, key: str) -> None:
		"""Count a binding as Builder renders it: text, or an attribute. A style binding shows nothing."""
		kind, prop = binding.get("type"), binding.get("property")
		if kind not in ("key", "attribute"):
			return
		self.keys.add(key)
		if kind == "attribute":
			self.by_attribute.setdefault(prop, set()).add(key)
			if prop == "href" and block.get("element") == "a":
				self.links.add(key)

	def binds(self, attribute: str, key: str) -> bool:
		return key in self.by_attribute.get(attribute, ())


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
		is_open = component in self.open_components
		definition = None if is_open else get_component_block(component, block.get("componentVersion"))
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
		hidden = set()
		for binding in get_bindings(block):
			target = (binding.get("property"), binding.get("type"))
			if binding.get("type") == "attribute":
				self.usage.attributes.add(binding.get("property"))
			if is_page_data(binding) and self.check_key(
				block, scope, binding, is_rendered=target not in hidden
			):
				# Builder falls back to an earlier binding of the property only while this one is empty.
				# A Commera key is taken as set; a key Commera does not own may be empty, so it hides nothing.
				hidden.add(target)
		self.usage.attributes.update(block.get("attributes") or {}, block.get("customAttributes") or {})
		visible = get_visibility(block)
		if visible and is_page_data(visible):
			self.resolve(block, scope, visible["key"])

	def check_key(self, block: dict, scope: Scope | None, binding: dict, is_rendered: bool) -> bool:
		"""Check one binding, and count it when Builder renders it. True when the key is one of Commera's."""
		key = binding["key"]
		shape = self.resolve(block, scope, key)
		if shape is MISSING:
			return False
		if is_rendered:
			self.usage.add(block, binding, scope.key(key))
		if isinstance(shape, list):
			self.report(block, f"'{key}' is a list. Repeat it with a repeater, then bind its item's keys.")
		elif isinstance(shape, dict):
			self.report(block, f"'{key}' is a group of keys. Bind one of: {', '.join(list_keys(shape))}.")
		return True

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
	"""The bindings Builder renders on the block, the one that wins first: a later entry beats an earlier one
	of the same property. A repeater shows no text of its own, and a block that does not repeat can also
	hold the older single `dataKey` binding, which every other binding beats."""
	bindings = get_dynamic_values(block)[::-1]
	if block.get("isRepeaterBlock"):
		return [binding for binding in bindings if binding.get("type") != "key"]
	data_key = block.get("dataKey") or {}
	return [*bindings, data_key] if data_key.get("key") else bindings


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
	merged["element"] = instance.get("element") or definition.get("element")
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
	"""The instance's children, each merged with the component block it points at. Builder renders only
	these: an instance with no children publishes empty."""
	own = {
		child.get("blockId"): child for child in definition.get("children") or [] if isinstance(child, dict)
	}
	merged = []
	for child in instance.get("children") or []:
		if not isinstance(child, dict):
			continue
		match = own.get(child.get("blockId")) or own.get(child.get("referenceBlockId"))
		merged.append(merge_instance(match, child) if match else child)
	return merged


def get_component_block(component: str | None, version: str | None = None) -> dict | None:
	"""The component's block: the version the instance is pinned to, or the latest when that one is gone."""
	if not component:
		return None
	raw = get_pinned_block(component, version) or frappe.db.get_value("Builder Component", component, "block")
	try:
		block = json.loads(raw) if raw else None
	except json.JSONDecodeError:
		return None
	return block if isinstance(block, dict) else None


def get_pinned_block(component: str, version: str | None) -> str | None:
	if not (version and frappe.db.table_exists(VERSION_DOCTYPE)):
		return None
	filters = {"name": version, "reference_doctype": "Builder Component", "reference_name": component}
	data = frappe.db.get_value(VERSION_DOCTYPE, {**filters, "snapshot_type": "Component Version"}, "data")
	return (frappe.parse_json(data) or {}).get("block") if data else None
