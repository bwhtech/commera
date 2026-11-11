"""What Bob, Builder's agent, is told about a Commera theme page, through the builder_agent_context hook."""

import json

import frappe

from commera.builder_themes.page_data import get_data_for
from commera.builder_themes.pages import (
	HOME,
	PRODUCT_DETAIL,
	PRODUCT_LISTING,
	STOREFRONT_PATHS,
	get_page_role,
	get_theme_pages,
)

SAMPLE_LIST_LENGTH = 2
SAMPLE_TEXT_LENGTH = 160

DATA_INTRO = """\
Commera puts this page's data under the "commera" key: bind commera.product.title, repeat(commera.products).
Inside a repeater, bind the item's own fields as usual (title, url, price). The keys:
"""

COMMON_KEYS = """\
- shop: name, description, logo, and finished links home_url, products_url, sale_url, search_url, cart_url, account_url.
- menu: the store menu, each {title, url, items[{title, url, items}]}.
- footer: footer sections, each {title, links[]}."""

CARD_FIELDS = (
	"title, url, image, hover_image, vendor, color, price, compare_at_price (empty unless on sale), "
	"is_on_sale, is_available, rating, review_count"
)

PAGE_KEYS = {
	HOME: f"""\
- featured_products: the newest products, each a card: {CARD_FIELDS}.
- sale_products: products on sale, the same card fields.
- collections: the store's collections, each {{title, url, image}}.""",
	PRODUCT_LISTING: f"""\
- title: the listing heading ("All products", the collection's name or the search).
- query, total: the search text and the number of products found.
- products: this page of products, each a card: {CARD_FIELDS}.
- collections: collection links, each {{title, url, is_active}}.
- filters: filter groups, each {{name, values[{{label, count, url, is_active}}]}}; a value's url toggles it.
- active_filters: applied filters, each {{label, url}} where url removes it; has_active_filters, clear_filters_url.
- sort_options: each {{label, url, is_active}}.
- pagination: page, last_page, has_previous, previous_url, has_next, next_url, pages[{{number, url, is_current}}].""",
	PRODUCT_DETAIL: f"""\
- product: title, vendor, description_html, url, price, is_available, image, images[{{url, thumbnail}}],
  color, color_label, colors[{{name, url, is_selected, is_available, swatch_color}}] (each colour is its own
  product page: link to it), has_sizes, sizes[{{name, variant_id, price, is_available}}], default_variant_id,
  collection {{title, url}}, rating, review_count.
- related_products: cards: {CARD_FIELDS}.""",
}

BEHAVIOURS = """\
The page already loads Commera's storefront script: add no script for these. Mark elements with attributes:
- [data-commera-cart-count]: its text becomes the cart's item count (put it in the header's cart link).
- Sizes: repeat(commera.product.sizes) with one button each, bind(data-commera-size=variant_id). The chosen one gets
  aria-pressed="true": style that state with a page CSS rule on [data-commera-size][aria-pressed="true"].
- The add-to-cart button: bind(data-commera-add-to-cart=commera.product.default_variant_id). It adds the
  chosen size, or that variant when the product has no sizes. A buy-now button binds data-commera-buy-now the
  same way, and adds then goes to checkout.
- [data-commera-cart-message]: an empty text element near the button that shows "Added to cart" or an error.
- Search: a form with action bound to commera.shop.search_url, method get, and a text input named "search"."""

CART_DRAWER = """A cart drawer (when the user asks for one, or a design calls for it) is yours to design and script. The cart
lives in the browser, so render it from a page JavaScript script, not from bindings:
- window.commera.cart.get() resolves to the cart, or null when there is none. update_lines([{line_id, qty}])
  sets quantities (qty 0 removes), remove_lines([line_id]) removes, go_to_checkout() goes to checkout. Every
  write resolves to the new cart and fires a window "commera:cart-updated" event with the cart as event.detail.
- After add to cart succeeds, window fires "commera:cart-added" with the cart as event.detail: open the drawer.
- Cart: lines[{line_id, qty, rate, amount, product{handle, title, variant_title, image} or null}],
  total_quantity, subtotal, total, currency, free_delivery_above (null when none), free_delivery_shortfall.
- Money: window.commera.format.money_text(amount, cart.currency). A line's product page is
  window.commera.url("/products/" + product.handle).
- Write text with textContent, never innerHTML. The drawer is a dialog: Escape and the backdrop close it,
  focus moves into it and back to the opener. Keep the bag link's href bound to commera.shop.cart_url as the fallback.
- Build it once, on the Home page, as one shared script (and the drawer's markup in the header component); on
  the other pages attach_page_script the same script so every page shares it."""

RULES = """\
Rules:
- The data is already on the page: bind to these keys. Never write a page data script, create DocTypes, seed
  sample data or query records to get products.
- Every value is display-ready: prices are formatted strings and every link is a finished url. Bind href to the
  url fields; never build product or filter links yourself.
- Text values are already HTML-escaped and description_html is HTML: bind them to innerHTML or an attribute,
  never to textContent from a script.
- Never change this page's route, head HTML or the site's home page, and never edit global settings: Commera
  serves this page at its storefront route.
- Design tokens are shared by the whole site. Prefix every token you create with "{prefix}-", and change no
  token without that prefix.
- Cart, checkout and account are Commera's own pages; link to them, never build them. A cart drawer is
  not a cart page: it is fine to build."""


def get_agent_context(page_id: str) -> str | None:
	"""The builder_agent_context hook: None for a page outside every Commera theme."""
	role = get_page_role(page_id)
	if not role:
		return None
	pages = get_theme_pages(role.theme)
	return "\n\n".join(
		[
			get_role_text(role, pages),
			DATA_INTRO + COMMON_KEYS + "\n" + PAGE_KEYS[role.page_type],
			"A trimmed sample of this page's real data:\n" + get_sample(role.page_type),
			BEHAVIOURS,
			CART_DRAWER,
			RULES.format(prefix=frappe.scrub(role.theme).replace("_", "-")),
		]
	)


def get_role_text(role, pages: dict) -> str:
	siblings = ", ".join(f"{page_type} (page id {name})" for page_type, name in pages.items())
	text = (
		f'This page is the {role.page_type} page of "{role.theme}", a storefront theme of Commera, the store\'s '
		f"ecommerce app. When the theme is live, shoppers see it at {STOREFRONT_PATHS[role.page_type]}. "
		f"The theme's pages are: {siblings}. Only these three pages are designed in Builder."
	)
	if role.page_type == HOME:
		return text + (
			" This is the theme's first page: its design sets the system the other two follow. Make the header"
			" and footer components (extract_component) so the other pages embed them instead of copying them."
		)
	return text + (
		f" Match the theme's Home page ({pages.get(HOME)}): read_page it first, reuse its design tokens and its "
		"header and footer components, and match it instead of asking design questions."
	)


def get_sample(page_type: str) -> str:
	try:
		data = get_data_for(page_type, {})
	except frappe.PageDoesNotExistError:
		return "(the store has no products yet)"
	return json.dumps({"commera": trim(data)}, indent=None, default=str)


def trim(value):
	if isinstance(value, dict):
		return {key: trim(item) for key, item in value.items()}
	if isinstance(value, list):
		return [trim(item) for item in value[:SAMPLE_LIST_LENGTH]]
	if isinstance(value, str) and len(value) > SAMPLE_TEXT_LENGTH:
		return value[:SAMPLE_TEXT_LENGTH] + "…"
	return value
