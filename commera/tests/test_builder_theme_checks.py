# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

"""The checks on a Builder theme page, and the tool that runs them for Bob."""

import unittest
from types import SimpleNamespace

import frappe

from commera.builder_themes.agent_context import get_agent_context
from commera.builder_themes.agent_tools import CHECK_PAGE
from commera.builder_themes.cards import get_card
from commera.builder_themes.checks import check_page
from commera.builder_themes.listing import Listing
from commera.builder_themes.page_data import (
	get_collection_link,
	get_data_for,
	get_menu_link,
	get_product_shape,
)
from commera.builder_themes.pages import (
	HOME,
	PRODUCT_DETAIL,
	PRODUCT_LISTING,
	get_theme_pages,
	is_builder_installed,
)
from commera.builder_themes.schema import CARD, MENU_LINK, PAGE_KEYS, ROOT_KEY, get_page_schema
from commera.builder_themes.theme import create_builder_theme
from commera.tests.test_product_details import ProductDetailPriceTestCase

THEME = "Test Checked Theme"


def block(element="div", *children, bind=None, attrs=None, repeat=None, visible=None, component=None):
	"""A Builder block as the editor saves it. `bind` maps a property to a key; text binds as innerHTML."""
	made = {"element": element, "blockId": frappe.generate_hash(length=8), "children": list(children)}
	if bind:
		made["dynamicValues"] = [
			{"key": key, "property": prop, "type": "key" if prop == "innerHTML" else "attribute"}
			for prop, key in bind.items()
		]
	if attrs:
		made["attributes"] = attrs
	if repeat:
		made["isRepeaterBlock"] = True
		made["dataKey"] = {"key": repeat, "property": "innerHTML", "type": "key"}
	if visible:
		made["visibilityCondition"] = {"key": visible, "comesFrom": "dataScript"}
	if component:
		made["extendedFromComponent"] = component
	return made


def header():
	count = block("span", attrs={"data-commera-cart-count": ""})
	return block("a", count, bind={"href": "commera.shop.cart_url"})


def card():
	return block("a", block("p", bind={"innerHTML": "title"}), bind={"href": "url"})


def product_page(*extra):
	size = block("button", bind={"data-commera-size": "variant_id", "innerHTML": "name"})
	return block(
		"div",
		header(),
		block("h1", bind={"innerHTML": "commera.product.title"}),
		block("p", bind={"innerHTML": "commera.product.price"}),
		block("img", bind={"src": "commera.product.image"}),
		block("div", size, repeat="commera.product.sizes"),
		block("button", bind={"data-commera-add-to-cart": "commera.product.default_variant_id"}),
		block("p", attrs={"data-commera-cart-message": ""}),
		block("div", card(), repeat="commera.related_products"),
		*extra,
	)


def listing_page(*extra):
	value = block("a", bind={"href": "url", "innerHTML": "label"})
	return block(
		"div",
		header(),
		block("div", card(), repeat="commera.products"),
		block("div", block("div", value, repeat="values"), repeat="commera.filters"),
		block("div", block("a", bind={"href": "url"}), repeat="commera.sort_options"),
		block("a", bind={"href": "commera.pagination.next_url"}, visible="commera.pagination.has_next"),
		*extra,
	)


def messages(problems, warnings=False):
	return [problem.message for problem in problems if problem.is_warning == warnings]


class TestThemePageChecks(ProductDetailPriceTestCase):
	def assert_one_problem(self, problems, *words):
		found = messages(problems)
		self.assertEqual(len(found), 1, found)
		for word in words:
			self.assertIn(word, found[0])

	def test_the_declared_keys_are_the_keys_the_page_data_has(self):
		self.make_priced_variant("CHECKED", default_rate=100, sale_rate=80)
		for page_type in (HOME, PRODUCT_LISTING, PRODUCT_DETAIL):
			with self.subTest(page_type=page_type):
				data = {ROOT_KEY: get_data_for(page_type, {})}
				self.assert_same_keys(data, get_page_schema(page_type), page_type)

	def test_every_declared_shape_is_what_its_producer_returns(self):
		"""Full inputs, so no list is empty and no group is missing: a renamed key cannot hide."""
		rating = {"average": 4.5, "count": 2}
		card = {
			"title": "Shirt",
			"handle": "shirt",
			"image": "/a.jpg",
			"hover_image": "/b.jpg",
			"vendor": "V",
		}
		card |= {"color": "Red", "price": 80, "compare_at_price": 100, "currency": "USD", "available": True}
		color = {"name": "Red", "handle": "shirt-red", "selected": True, "available": True}
		variants = [{"id": f"SKU-{size}", "title": size, "price": 80, "available": True} for size in "SM"]
		product = card | {
			"description_html": "<p>Soft</p>",
			"images": ["/a.jpg"],
			"options": [{"name": "Colour", "values": [color | {"swatch": {"color": "#f00"}}]}],
			"variants": variants,
			"collection": {"title": "Shirts", "handle": "shirts"},
			"rating": rating,
		}
		listing = Listing({"colors": "Red", "has_discount": "1"})
		made = {
			"card": (get_card(card | {"rating": rating}), CARD),
			"product": (get_product_shape(product), PAGE_KEYS[PRODUCT_DETAIL]["product"]),
			"menu": (get_menu_link({"title": "Men", "url": "/men", "items": []}), MENU_LINK),
			"collection": (
				get_collection_link({"title": "Shirts", "handle": "shirts", "image": "/a.jpg"}),
				PAGE_KEYS[HOME]["collections"][0],
			),
			"filters": (
				listing.get_filters({"colors": [{"value": "Red", "count": 1}]}),
				PAGE_KEYS[PRODUCT_LISTING]["filters"],
			),
			"active_filters": (listing.get_active_filters(), PAGE_KEYS[PRODUCT_LISTING]["active_filters"]),
			"pagination": (listing.get_pagination(2), PAGE_KEYS[PRODUCT_LISTING]["pagination"]),
			"collections": (listing.get_collection_links(), PAGE_KEYS[PRODUCT_LISTING]["collections"]),
		}
		for name, (value, shape) in made.items():
			with self.subTest(name=name):
				self.assert_same_keys(value, shape, name, is_full=True)

	def assert_same_keys(self, value, shape, path, is_full=False):
		if isinstance(shape, list):
			self.assertIsInstance(value, list, path)
			self.assertTrue(value or not is_full, f"{path} is empty")
			for item in value:
				self.assert_same_keys(item, shape[0], f"{path}[]", is_full)
		elif isinstance(shape, dict) and (value is not None or is_full):
			self.assertEqual(set(value), set(shape), path)
			for key, item in value.items():
				# a menu link holds menu links without end: one level is enough
				if shape[key] != [shape]:
					self.assert_same_keys(item, shape[key], f"{path}.{key}", is_full)
		else:
			self.assertNotIsInstance(value, (list, dict), path)

	def test_a_complete_page_passes(self):
		self.assertEqual(check_page(PRODUCT_DETAIL, product_page()), [])
		self.assertEqual(check_page(PRODUCT_LISTING, listing_page()), [])
		home = block("div", header(), block("div", card(), repeat="commera.featured_products"))
		self.assertEqual(check_page(HOME, home), [])

	def test_an_empty_page_is_one_problem(self):
		self.assert_one_problem(check_page(HOME, block("div")), "empty")
		self.assert_one_problem(check_page(HOME, None), "empty")

	def test_a_wrong_key_names_its_block_and_the_close_key(self):
		wrong = block("p", bind={"innerHTML": "commera.product.titel"})
		problems = check_page(PRODUCT_DETAIL, product_page(wrong))
		self.assert_one_problem(problems, "'commera.product.titel'", "Did you mean 'commera.product.title'?")
		self.assertEqual(problems[0].block, wrong["blockId"])

	def test_a_key_of_another_page_type_is_wrong_here(self):
		wrong = block("p", bind={"innerHTML": "commera.product.title"})
		problems = check_page(HOME, block("div", header(), wrong))
		self.assert_one_problem(problems, "not a key of the Home page")

	def test_a_key_without_the_prefix_is_told_to_add_it(self):
		wrong = block("p", bind={"innerHTML": "shop.name"})
		problems = check_page(PRODUCT_DETAIL, product_page(wrong))
		self.assert_one_problem(problems, "bind 'commera.shop.name'")

	def test_a_key_commera_does_not_own_is_left_alone(self):
		own = block("p", bind={"innerHTML": "merchant_note"})
		props = block("p")
		props["dynamicValues"] = [
			{"key": "titel", "property": "innerHTML", "type": "key", "comesFrom": "props"}
		]
		self.assertEqual(check_page(PRODUCT_DETAIL, product_page(own, props)), [])

	def test_a_repeater_reads_only_its_items_keys(self):
		outside = block("p", bind={"innerHTML": "commera.shop.name"})
		typo = block("p", bind={"innerHTML": "pirce"})
		cards = block("div", block("div", card(), outside, typo), repeat="commera.related_products")
		found = messages(check_page(PRODUCT_DETAIL, product_page(cards)))
		self.assertEqual(len(found), 2, found)
		self.assertIn("reads only its item's keys", found[0])
		self.assertIn("Did you mean 'price'?", found[1])

	def test_a_list_or_a_group_cannot_be_bound_as_text(self):
		a_list = block("p", bind={"innerHTML": "commera.product.sizes"})
		a_group = block("p", bind={"innerHTML": "commera.product.collection"})
		found = messages(check_page(PRODUCT_DETAIL, product_page(a_list, a_group)))
		self.assertEqual(len(found), 2, found)
		self.assertIn("is a list", found[0])
		self.assertIn("Bind one of: title, url", found[1])

	def test_a_repeater_needs_a_list(self):
		wrong = block("div", block("p"), repeat="commera.product.title")
		self.assert_one_problem(check_page(PRODUCT_DETAIL, product_page(wrong)), "is not a list")

	def test_a_product_page_needs_its_buying_parts(self):
		page = block("div", header(), block("h1", bind={"innerHTML": "commera.product.title"}))
		found = messages(check_page(PRODUCT_DETAIL, page))
		self.assertEqual(len(found), 3, found)
		self.assertIn("price is not bound", found[0])
		self.assertIn("data-commera-add-to-cart", found[1])
		self.assertIn("data-commera-size", found[2])

	def test_a_typed_add_to_cart_attribute_does_not_count(self):
		page = product_page()
		button = next(child for child in page["children"] if child["element"] == "button")
		button["dynamicValues"] = []
		button["attributes"] = {"data-commera-add-to-cart": "SKU-1"}
		self.assert_one_problem(check_page(PRODUCT_DETAIL, page), "No working add-to-cart button")

	def test_a_listing_needs_products_and_pagination(self):
		found = messages(check_page(PRODUCT_LISTING, block("div", header(), block("h1"))))
		self.assertEqual(len(found), 2, found)
		self.assertIn("Repeat commera.products", found[0])
		self.assertIn("pagination", found[1])

	def test_cards_must_link_to_their_product(self):
		unlinked = block("div", block("p", bind={"innerHTML": "title"}), repeat="commera.featured_products")
		problems = check_page(HOME, block("div", header(), unlinked))
		self.assert_one_problem(problems, "'commera.featured_products' do not link")

	def test_missing_optional_parts_and_typed_links_are_warnings(self):
		page = block(
			"div",
			block("a", bind={"href": "commera.shop.cart_url"}),
			block("a", attrs={"href": "/products"}),
			block("a", attrs={"href": "https://example.com"}),
		)
		problems = check_page(HOME, page)
		self.assertEqual(messages(problems), [])
		found = messages(problems, warnings=True)
		self.assertEqual(len(found), 3, found)
		self.assertTrue(any("'/products' is typed in" in message for message in found))

	def test_older_binding_forms_are_read_as_builder_reads_them(self):
		page = product_page()
		cart = page["children"][0]
		cart["dynamicValues"] = []
		cart["dataKey"] = {"key": "commera.shop.cart_url", "property": "href", "type": "attribute"}
		self.assertEqual(check_page(PRODUCT_DETAIL, page), [])

		bare = block("p")
		bare["dynamicValues"] = ["commera.shop.nmae"]
		hidden = block("p")
		hidden["visibilityCondition"] = "commera.product.is_availble"
		found = messages(check_page(PRODUCT_DETAIL, product_page(bare, hidden)))
		self.assertEqual(len(found), 2, found)
		self.assertIn("Did you mean 'commera.shop.name'?", found[0])
		self.assertIn("Did you mean 'commera.product.is_available'?", found[1])

	def test_only_a_repeaters_first_child_counts(self):
		title = block("p", bind={"innerHTML": "title"})
		cards = block("div", title, card(), repeat="commera.featured_products")
		problems = check_page(HOME, block("div", header(), cards))
		self.assert_one_problem(problems, "'commera.featured_products' do not link")

	def test_a_repeater_on_props_keeps_the_page_keys(self):
		wrong = block("p", bind={"innerHTML": "commera.product.titel"})
		tabs = block("div", wrong, repeat="tabs")
		tabs["dataKey"]["comesFrom"] = "props"
		self.assert_one_problem(check_page(PRODUCT_DETAIL, product_page(tabs)), "'commera.product.titel'")

	def test_a_part_needs_a_link_not_only_its_key(self):
		tooltip = block("div", bind={"title": "commera.shop.cart_url"})
		home = block("div", tooltip, block("div", card(), repeat="commera.featured_products"))
		self.assert_one_problem(check_page(HOME, home), "No link to the cart")

		page = listing_page()
		page["children"][-1] = block("p", bind={"innerHTML": "commera.pagination.page"})
		self.assert_one_problem(check_page(PRODUCT_LISTING, page), "No pagination links")
		number = block("a", bind={"href": "url", "innerHTML": "number"})
		page["children"][-1] = block("div", number, repeat="commera.pagination.pages")
		self.assertEqual(check_page(PRODUCT_LISTING, page), [])

	def test_a_link_is_an_anchor_with_a_bound_href(self):
		products = block("div", card(), repeat="commera.featured_products")
		not_an_anchor = block("div", bind={"href": "commera.shop.cart_url"})
		self.assert_one_problem(
			check_page(HOME, block("div", not_an_anchor, products)), "No link to the cart"
		)
		styled = block("a")
		styled["dynamicValues"] = [{"key": "commera.shop.cart_url", "property": "href", "type": "style"}]
		self.assert_one_problem(check_page(HOME, block("div", styled, products)), "No link to the cart")

	def test_a_repeaters_own_text_binding_is_not_rendered_so_not_checked(self):
		products = block("div", card(), repeat="commera.featured_products")
		products["dynamicValues"] = [{"key": "commera.shop.nmae", "property": "innerHTML", "type": "key"}]
		self.assertEqual(check_page(HOME, block("div", header(), products)), [])

	def test_custom_attributes_count(self):
		page = product_page()
		for child in page["children"]:
			if "data-commera-cart-message" in child.get("attributes", {}):
				child["customAttributes"] = child.pop("attributes")
		self.assertEqual(check_page(PRODUCT_DETAIL, page), [])


@unittest.skipUnless(is_builder_installed(), "Frappe Builder is not installed on this site")
class TestBobChecksThemePages(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.db.rollback)
		create_builder_theme(THEME)
		self.pages = get_theme_pages(THEME)

	def get_tool(self):
		from builder.ai.agent.registry import build_default_registry

		return build_default_registry().get(CHECK_PAGE)

	def check(self, page_type, root, **args):
		from builder.ai.agent.tree import WorkingTree

		ctx = SimpleNamespace(page_id=self.pages[page_type], tree=WorkingTree(root))
		return self.get_tool().handler(ctx, args)

	def save_draft(self, page_type, root):
		frappe.db.set_value("Builder Page", self.pages[page_type], "draft_blocks", frappe.as_json([root]))

	def test_bob_gets_the_tool_only_on_a_theme_page(self):
		tool = self.get_tool()
		self.assertTrue(tool.available(SimpleNamespace(page_id=self.pages[HOME])))
		other = frappe.get_doc({"doctype": "Builder Page", "page_title": "Not a theme page"}).insert()
		self.assertFalse(tool.available(SimpleNamespace(page_id=other.name)))

	def test_bob_is_told_to_check_before_it_finishes(self):
		self.assertIn(f"call {CHECK_PAGE}", get_agent_context(self.pages[HOME]))

	def test_the_tool_checks_this_turns_edits_not_the_saved_page(self):
		self.save_draft(PRODUCT_DETAIL, product_page())
		wrong = block("p", bind={"innerHTML": "commera.product.titel"})
		reply = self.check(PRODUCT_DETAIL, product_page(wrong))
		self.assertTrue(reply.startswith("FAILED: 1 to fix on the Product Detail page"), reply)
		self.assertIn(f"- block {wrong['blockId']}: 'commera.product.titel'", reply)

	def test_the_tool_checks_another_theme_page_as_saved(self):
		self.save_draft(PRODUCT_LISTING, listing_page())
		reply = self.check(HOME, block("div"), page=self.pages[PRODUCT_LISTING])
		self.assertEqual(reply, "OK: the Product Listing page passes Commera's checks.")

	def test_the_tool_checks_the_edits_held_for_another_theme_page(self):
		from builder.ai.agent.tree import WorkingTree

		listing = self.pages[PRODUCT_LISTING]
		held = SimpleNamespace(tree_of=lambda page: WorkingTree(listing_page()) if page == listing else None)
		ctx = SimpleNamespace(page_id=self.pages[HOME], tree=WorkingTree(block("div")), page_changes=held)
		reply = self.get_tool().handler(ctx, {"page": listing})
		self.assertEqual(reply, "OK: the Product Listing page passes Commera's checks.")

	def test_warnings_alone_do_not_fail(self):
		page = product_page(block("a", attrs={"href": "/cart"}))
		reply = self.check(PRODUCT_DETAIL, page)
		self.assertTrue(reply.startswith("OK: the Product Detail page has no problems."), reply)
		self.assertIn("'/cart' is typed in", reply)

	def test_a_page_outside_every_theme_is_refused(self):
		other = frappe.get_doc({"doctype": "Builder Page", "page_title": "Not a theme page"}).insert()
		reply = self.check(HOME, block("div"), page=other.name)
		self.assertEqual(reply, f"FAILED: {other.name} is not a page of a Commera theme.")
		self.assertTrue(self.check(HOME, block("div"), page="no such page").startswith("FAILED:"))

	def test_a_component_is_checked_with_the_page(self):
		wrong = block("p", bind={"innerHTML": "commera.shop.nmae"})
		component = frappe.get_doc(
			{
				"doctype": "Builder Component",
				"component_name": "Checked Header",
				"block": frappe.as_json(block("div", header(), wrong)),
			}
		).insert()
		page = product_page()
		page["children"][0] = block("div", component=component.name)
		reply = self.check(PRODUCT_DETAIL, page)
		self.assertTrue(reply.startswith("FAILED: 1 to fix"), reply)
		self.assertIn(f"- block {wrong['blockId']} of component {component.name}: 'commera.shop.nmae'", reply)

	def make_component(self, name, root):
		component = {"doctype": "Builder Component", "component_name": name, "block": frappe.as_json(root)}
		return frappe.get_doc(component).insert().name

	def test_an_instance_is_checked_with_what_the_page_changes_on_it(self):
		cart = header()
		name = block("p", bind={"innerHTML": "commera.shop.nmae"})
		component = self.make_component("Checked Shop Name", block("div", cart, name))

		def instance(key):
			"""The component on a page, which binds its name block to another key."""
			changed = block("p", bind={"innerHTML": key})
			changed["referenceBlockId"] = name["blockId"]
			kept = block("a")
			kept["referenceBlockId"] = cart["blockId"]
			return block("div", kept, changed, component=component)

		page = product_page()
		page["children"][0] = instance("commera.shop.name")
		self.assertEqual(
			self.check(PRODUCT_DETAIL, page), "OK: the Product Detail page passes Commera's checks."
		)
		page["children"][0] = instance("commera.shop.nam")
		self.assertIn("'commera.shop.nam' is not a key", self.check(PRODUCT_DETAIL, page))

	def test_a_component_is_checked_in_each_place_it_is_used(self):
		component = self.make_component("Checked Card", card())
		home = block(
			"div",
			header(),
			block("div", block("a", component=component), repeat="commera.featured_products"),
			block("div", block("a", component=component), repeat="commera.sale_products"),
		)
		self.assertEqual(self.check(HOME, home), "OK: the Home page passes Commera's checks.")
		home["children"].append(block("div", block("a", component=component), repeat="commera.footer"))
		self.assertIn("'url' is not a key of an item of 'commera.footer'", self.check(HOME, home))

	def test_a_page_the_user_cannot_read_does_not_show_its_role(self):
		other = frappe.get_doc({"doctype": "Builder Page", "page_title": "Not a theme page"}).insert()
		user = frappe.get_doc(
			{"doctype": "User", "email": "no-builder@example.com", "first_name": "No Builder"}
		).insert(ignore_permissions=True)
		frappe.set_user(user.name)
		self.addCleanup(frappe.set_user, "Administrator")
		for page in (self.pages[PRODUCT_LISTING], other.name):
			reply = self.check(HOME, block("div"), page=page)
			self.assertEqual(reply, f"FAILED: you cannot read page {page}.")

	def test_an_instance_pinned_to_a_version_is_checked_as_that_version(self):
		wrong = block("div", header(), block("p", bind={"innerHTML": "commera.shop.nmae"}))
		component = self.make_component("Checked Pinned Header", wrong)
		right = block("div", header(), block("p", bind={"innerHTML": "commera.shop.name"}))
		version = frappe.get_doc(
			{
				"doctype": "Builder Snapshot",
				"reference_doctype": "Builder Component",
				"reference_name": component,
				"snapshot_type": "Component Version",
				"data": frappe.as_json({"block": frappe.as_json(right)}),
			}
		).insert()
		page = product_page()
		page["children"][0] = block("div", component=component)
		self.assertIn("'commera.shop.nmae'", self.check(PRODUCT_DETAIL, page))
		page["children"][0]["componentVersion"] = version.name
		self.assertEqual(
			self.check(PRODUCT_DETAIL, page), "OK: the Product Detail page passes Commera's checks."
		)
		page["children"][0]["componentVersion"] = "a version that is gone"
		self.assertIn("'commera.shop.nmae'", self.check(PRODUCT_DETAIL, page))
