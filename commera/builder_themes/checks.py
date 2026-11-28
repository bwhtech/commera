"""Checks a theme page's blocks: do its bindings name real keys, and does it have what a store page needs?

One checker for every caller (Bob's tool today), so a page built by hand and one Bob built meet the same rules.
"""

import json
from dataclasses import dataclass, field
from difflib import get_close_matches

import frappe

from commera.builder_themes.pages import HOME, PRODUCT_DETAIL, PRODUCT_LISTING
from commera.builder_themes.schema import MISSING, ROOT_KEY, get_page_schema, list_keys, resolve

PAGE_DATA_SOURCE = "dataScript"
CARD_LISTS = ("featured_products", "sale_products", "products", "related_products")


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


def check_page(page_type: str, root: dict | None) -> list[Problem]:
	"""Problems first, then warnings. An empty list means the page passes."""
	if not (root and root.get("children")):
		return [Problem("The page is empty: it has no blocks yet.")]
	walk = BlockWalk(page_type)
	walk.visit(root, Scope(get_page_schema(page_type)))
	problems = walk.problems + RequiredParts(page_type, walk.usage).check()
	return sorted(problems, key=lambda problem: problem.is_warning)


class BlockWalk:
	"""Visits every block, components included, and checks each binding against the keys in its scope."""

	def __init__(self, page_type: str):
		self.page_type = page_type
		self.usage = Usage()
		self.problems: list[Problem] = []
		self.component = None
		self.seen_components: set[str] = set()

	def visit(self, block: dict, scope: Scope | None) -> None:
		self.check_bindings(block, scope)
		self.check_typed_link(block)
		inner = self.get_repeater_scope(block, scope)
		if component := block.get("extendedFromComponent"):
			# an instance's children only point at the component's blocks
			self.visit_component(component, inner)
			return
		for child in block.get("children") or []:
			if isinstance(child, dict):
				self.visit(child, inner)

	def visit_component(self, component: str, scope: Scope | None) -> None:
		if component in self.seen_components:
			return
		self.seen_components.add(component)
		root = get_component_block(component)
		if not root:
			return
		outer, self.component = self.component, component
		self.visit(root, scope)
		self.component = outer

	def check_bindings(self, block: dict, scope: Scope | None) -> None:
		for binding in block.get("dynamicValues") or []:
			prop = binding.get("property") or ""
			if binding.get("type") == "attribute":
				self.usage.attributes.add(prop)
			if is_page_data(binding):
				self.check_key(block, scope, binding.get("key") or "", prop)
		for name in block.get("attributes") or {}:
			self.usage.attributes.add(name)
		visible = block.get("visibilityCondition")
		if isinstance(visible, dict) and is_page_data(visible):
			self.check_key(block, scope, visible.get("key") or "", "visible")

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

	def get_repeater_scope(self, block: dict, scope: Scope | None) -> Scope | None:
		"""The scope of a repeater's children, or the block's own scope when it does not repeat."""
		data_key = block.get("dataKey") or {}
		key = data_key.get("key")
		if not (block.get("isRepeaterBlock") and key):
			return scope
		if not is_page_data(data_key):
			return None
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
		is_bound = any(binding.get("property") == "href" for binding in block.get("dynamicValues") or [])
		if isinstance(href, str) and href.startswith("/") and not href.startswith("//") and not is_bound:
			self.report(
				block,
				f"The link '{href}' is typed in. Bind href to a url key (commera.shop.products_url, an item's "
				"url): a typed path breaks when the store adds a language prefix.",
				is_warning=True,
			)

	def report(self, block: dict, message: str, is_warning: bool = False) -> None:
		self.problems.append(Problem(message, block.get("blockId"), self.component, is_warning))


class RequiredParts:
	"""The parts each page type needs to work as a store page, checked against what the page binds."""

	def __init__(self, page_type: str, usage: Usage):
		self.page_type = page_type
		self.usage = usage
		self.problems: list[Problem] = []

	def check(self) -> list[Problem]:
		self.check_shared_parts()
		self.check_card_links()
		{HOME: self.check_home, PRODUCT_LISTING: self.check_listing, PRODUCT_DETAIL: self.check_product}[
			self.page_type
		]()
		return self.problems

	def check_shared_parts(self) -> None:
		self.need(
			"commera.shop.cart_url" in self.usage.keys,
			"No link to the cart. Bind a link's href to commera.shop.cart_url, in the header.",
		)
		self.need(
			"data-commera-cart-count" in self.usage.attributes,
			"No cart count. Give an element in the cart link the attribute data-commera-cart-count.",
			is_warning=True,
		)

	def check_card_links(self) -> None:
		for name in CARD_LISTS:
			path = f"{ROOT_KEY}.{name}"
			self.need(
				path not in self.usage.repeated or self.usage.binds("href", f"{path}.url"),
				f"The cards of '{path}' do not link to their product. Bind a link's href to the item's url.",
			)

	def check_home(self) -> None:
		lists = {f"{ROOT_KEY}.{name}" for name in ("featured_products", "sale_products", "collections")}
		self.need(
			bool(lists & self.usage.repeated),
			"The home page shows no products or collections. Repeat commera.featured_products, "
			"commera.sale_products or commera.collections.",
			is_warning=True,
		)

	def check_listing(self) -> None:
		self.need(
			"commera.products" in self.usage.repeated,
			"The listing shows no products. Repeat commera.products with one card as the item.",
		)
		self.need(
			any(key.startswith("commera.pagination.") for key in self.usage.keys | self.usage.repeated),
			"No pagination, so shoppers cannot go past the first page. Bind links to "
			"commera.pagination.previous_url and next_url, or repeat commera.pagination.pages.",
		)
		self.need(
			"commera.filters" in self.usage.repeated,
			"No filters. Repeat commera.filters, and its values inside it.",
			is_warning=True,
		)
		self.need(
			"commera.sort_options" in self.usage.repeated,
			"No sort options. Repeat commera.sort_options.",
			is_warning=True,
		)

	def check_product(self) -> None:
		for key in ("title", "price"):
			self.need(
				f"commera.product.{key}" in self.usage.keys,
				f"The product's {key} is not bound, so every product shows the same typed text. "
				f"Bind it to commera.product.{key}.",
			)
		self.need(
			self.usage.binds("data-commera-add-to-cart", "commera.product.default_variant_id"),
			"No working add-to-cart button. Bind the button's data-commera-add-to-cart attribute to "
			"commera.product.default_variant_id.",
		)
		self.need(
			self.usage.binds("data-commera-size", "commera.product.sizes.variant_id"),
			"No size picker, so a product with sizes cannot be added to the cart. Repeat "
			"commera.product.sizes with one button, and bind its data-commera-size attribute to variant_id.",
		)
		self.need(
			bool(
				{"commera.product.image", "commera.product.images"} & (self.usage.keys | self.usage.repeated)
			),
			"The product's image is not bound. Bind an image's src to commera.product.image, or repeat "
			"commera.product.images.",
			is_warning=True,
		)
		self.need(
			"data-commera-cart-message" in self.usage.attributes,
			"No cart message. Add an empty text element with the attribute data-commera-cart-message near "
			"the button: it shows 'Choose a size first' and errors.",
			is_warning=True,
		)

	def need(self, is_met: bool, message: str, is_warning: bool = False) -> None:
		if not is_met:
			self.problems.append(Problem(message, is_warning=is_warning))


def is_page_data(binding: dict) -> bool:
	"""False for a binding to a component's props or its own data, which Commera does not own."""
	return binding.get("comesFrom", PAGE_DATA_SOURCE) == PAGE_DATA_SOURCE


def suggest(scope: Scope, key: str) -> str:
	close = get_close_matches(key, list_keys(scope.shape), n=1)
	return f" Did you mean '{close[0]}'?" if close else ""


def get_component_block(component: str) -> dict | None:
	raw = frappe.db.get_value("Builder Component", component, "block")
	try:
		block = json.loads(raw) if raw else None
	except json.JSONDecodeError:
		return None
	return block if isinstance(block, dict) else None
