"""Checks a theme page's blocks: do its bindings name real keys, and does it have what a store page needs?

One checker for every caller (Bob's tool today), so a page built by hand and one Bob built meet the same rules.
"""

from commera.builder_themes.block_walk import BlockWalk, Problem, Scope, Usage
from commera.builder_themes.pages import HOME, PRODUCT_DETAIL, PRODUCT_LISTING
from commera.builder_themes.schema import ROOT_KEY, get_page_schema

CARD_LISTS = ("featured_products", "sale_products", "products", "related_products")


def check_page(page_type: str, root: dict | None) -> list[Problem]:
	"""Problems first, then warnings. An empty list means the page passes."""
	if not (root and root.get("children")):
		return [Problem("The page is empty: it has no blocks yet.")]
	walk = BlockWalk(page_type)
	walk.visit(root, Scope(get_page_schema(page_type)))
	problems = walk.problems + RequiredParts(page_type, walk.usage).check()
	return sorted(problems, key=lambda problem: problem.is_warning)


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
			self.usage.binds("href", "commera.shop.cart_url"),
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
			self.usage.binds("href", "commera.pagination.next_url")
			or self.usage.binds("href", "commera.pagination.pages.url"),
			"No pagination links, so shoppers cannot go past the first page. Bind links' href to "
			"commera.pagination.previous_url and next_url, or repeat commera.pagination.pages with a link "
			"bound to the item's url.",
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
