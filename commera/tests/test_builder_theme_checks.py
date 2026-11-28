# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

"""The checks on a Builder theme page, and the tool that runs them for Bob."""

import unittest
from types import SimpleNamespace

import frappe

from commera.builder_themes.agent_context import get_agent_context
from commera.builder_themes.agent_tools import CHECK_PAGE
from commera.builder_themes.checks import check_page
from commera.builder_themes.page_data import get_data_for
from commera.builder_themes.pages import (
	HOME,
	PRODUCT_DETAIL,
	PRODUCT_LISTING,
	get_theme_pages,
	is_builder_installed,
)
from commera.builder_themes.schema import ROOT_KEY, get_page_schema
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

	def assert_same_keys(self, value, shape, path):
		if isinstance(shape, list):
			self.assertIsInstance(value, list, path)
			for item in value:
				self.assert_same_keys(item, shape[0], f"{path}[]")
		elif isinstance(shape, dict) and value is not None:
			self.assertEqual(set(value), set(shape), path)
			for key, item in value.items():
				self.assert_same_keys(item, shape[key], f"{path}.{key}")
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
		cards = block("div", card(), outside, typo, repeat="commera.related_products")
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
