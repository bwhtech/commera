# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

"""End-to-end flow cover for the navbar-off-Item-Group refactor. Snapshots are a full ``SELECT *``:
the five nav Custom Fields were removed without their columns, so a stray write still succeeds in SQL."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.nestedset import get_descendants_of, get_root_of, rebuild_tree

from commera.commera_ecommerce.doctype.commera_settings.navbar import navbar_manager
from commera.commera_ecommerce.doctype.ecommerce_category.ecommerce_category import (
	ITEM_GROUP_LINK_DOCTYPE,
	MAX_MENU_DEPTH,
	get_item_groups_by_entry,
	get_menu_tree,
)
from commera.tests import delete_menu_entries

PREFIX = "Test NF"


def find_node(menu, name):
	for node in menu:
		if node["name"] == name:
			return node
		found = find_node(node["children"], name)
		if found:
			return found
	return None


def labels_in_order(menu):
	"""Flatten the tree to ``["Men", "Men > Clothing", ...]`` so a whole shape fits one assertion."""
	paths = []

	def walk(node, trail):
		path = f"{trail} > {node['label']}" if trail else node["label"]
		paths.append(path)
		for child in node["children"]:
			walk(child, path)

	for root in menu:
		walk(root, "")
	return paths


class TestNavbarFlow(IntegrationTestCase):
	def setUp(self):
		# Per-class rollback: every test shares one transaction, so fixture names carry a hash.
		self.tag = frappe.generate_hash(length=8)
		self.catalog = self.make_item_group(f"{PREFIX} Catalog {self.tag}")
		self.clothing = self.make_item_group(f"{PREFIX} Clothing {self.tag}", self.catalog)
		self.shirts = self.make_item_group(f"{PREFIX} Shirts {self.tag}", self.clothing)
		self.too_deep = self.make_item_group(f"{PREFIX} Too Deep {self.tag}", self.shirts)
		self.bags = self.make_item_group(f"{PREFIX} Bags {self.tag}", self.catalog)
		self.brand = frappe.get_doc({"doctype": "Brand", "brand": f"{PREFIX} Brand {self.tag}"}).insert().name

	def tearDown(self):
		delete_menu_entries({"name": ["like", f"{PREFIX}%"]})
		frappe.db.delete("Item Group", {"name": ["like", f"{PREFIX}%"]})
		frappe.db.delete("Brand", {"name": ["like", f"{PREFIX}%"]})
		# Raw deletes skip the nested-set bookkeeping, so both trees are repaired for the next test.
		rebuild_tree("Item Group")
		rebuild_tree("Ecommerce Category")

	def make_item_group(self, name, parent=None):
		return (
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": name,
					# commera makes the storefront display name mandatory on Item Group.
					"custom_displayname": name,
					"parent_item_group": parent or get_root_of("Item Group"),
					"is_group": 1,
				}
			)
			.insert()
			.name
		)

	def add_node(self, parent, display_name, link_type=None, link_target=None):
		navbar_manager.add_node(
			parent=parent, display_name=display_name, link_type=link_type, link_target=link_target
		)
		return frappe.get_all(
			"Ecommerce Category",
			filters={"parent_ecommerce_category": parent or "", "display_name": display_name},
			order_by="creation desc",
			limit=1,
			pluck="name",
		)[0]

	def master_data_snapshot(self):
		"""Every column of every Item Group and Brand row, so any write at all shows up as a diff."""
		return {
			"Item Group": frappe.db.sql("select * from `tabItem Group` order by name", as_dict=True),
			"Brand": frappe.db.sql("select * from `tabBrand` order by name", as_dict=True),
		}

	def assert_master_data_untouched(self, before):
		after = self.master_data_snapshot()
		for doctype in ("Item Group", "Brand"):
			self.assertEqual(
				len(before[doctype]),
				len(after[doctype]),
				f"{doctype} row count changed: {len(before[doctype])} -> {len(after[doctype])}",
			)
			for old_row, new_row in zip(before[doctype], after[doctype], strict=True):
				changed = {
					field: (old_row[field], new_row[field])
					for field in old_row
					if old_row[field] != new_row[field]
				}
				self.assertEqual(changed, {}, f"{doctype} {old_row['name']} was written to: {changed}")

	def nested_set_problems(self, doctype="Ecommerce Category", parent_field="parent_ecommerce_category"):
		rows = [
			frappe._dict(row, parent_ecommerce_category=row.get(parent_field))
			for row in frappe.get_all(
				doctype, fields=["name", "lft", "rgt", parent_field], limit_page_length=0
			)
		]
		by_name = {row.name: row for row in rows}
		problems = []
		for row in rows:
			if not row.lft or not row.rgt or row.lft >= row.rgt:
				problems.append(f"{row.name}: bad bounds {row.lft}/{row.rgt}")
			parent = by_name.get(row.parent_ecommerce_category)
			if row.parent_ecommerce_category and not parent:
				problems.append(f"{row.name}: parent {row.parent_ecommerce_category} is missing")
			elif parent and not (parent.lft < row.lft and row.rgt < parent.rgt):
				problems.append(
					f"{row.name} {row.lft}/{row.rgt} sits outside its parent "
					f"{parent.name} {parent.lft}/{parent.rgt}"
				)
			if not row.parent_ecommerce_category:
				for other in rows:
					if other.name != row.name and not other.parent_ecommerce_category:
						if other.lft < row.lft < other.rgt:
							problems.append(
								f"root {row.name} {row.lft}/{row.rgt} is nested inside "
								f"root {other.name} {other.lft}/{other.rgt}"
							)
		bounds = sorted([row.lft for row in rows] + [row.rgt for row in rows])
		expected = list(range(1, 2 * len(rows) + 1))
		if bounds != expected:
			problems.append(
				f"bounds are not contiguous 1..{2 * len(rows)}: {sorted(set(expected) - set(bounds))} missing"
			)
		return problems

	def assert_nested_set_valid(self, stage):
		self.assertEqual(self.nested_set_problems(), [], f"nested set is inconsistent {stage}")

	def test_a_full_editor_session_writes_nothing_to_item_group_or_brand(self):
		"""Add, rename, reorder, move across parents, hide, delete and import, all in one session."""
		men = self.add_node(None, f"{PREFIX} Men {self.tag}")
		women = self.add_node(None, f"{PREFIX} Women {self.tag}")
		accessories = self.add_node(men, f"{PREFIX} Accessories")
		bags = self.add_node(accessories, f"{PREFIX} Bags", "Item Group", [self.bags])
		brand_tab = self.add_node(women, f"{PREFIX} Brand Tab", "Brand", self.brand)

		before = self.master_data_snapshot()
		shape_before = labels_in_order(navbar_manager.get_menu_editor_data()["menu"])

		navbar_manager.update_node(bags, display_name=f"{PREFIX} Handbags")
		navbar_manager.update_node(brand_tab, link_type="Item Group", link_target=[self.shirts])
		navbar_manager.reorder_nodes("", [women, men])
		navbar_manager.move_node(accessories, women, 0)
		navbar_manager.set_visibility(brand_tab, 0)
		navbar_manager.add_node(parent=men, display_name=f"{PREFIX} Shoes")
		navbar_manager.import_from_item_group(item_group=self.catalog, parent=men)
		navbar_manager.delete_node(bags)

		self.assert_master_data_untouched(before)

		# Guard against a vacuous pass: the session has to have actually rearranged the menu.
		shape_after = labels_in_order(navbar_manager.get_menu_editor_data()["menu"])
		self.assertNotEqual(shape_before, shape_after)
		self.assertFalse(frappe.db.exists("Ecommerce Category", bags))
		self.assertEqual(
			frappe.db.get_value("Ecommerce Category", accessories, "parent_ecommerce_category"), women
		)
		self.assert_nested_set_valid("after a full editor session")

	def test_importing_every_top_level_group_writes_nothing_to_item_group(self):
		before = self.master_data_snapshot()

		navbar_manager.import_from_item_group()

		self.assert_master_data_untouched(before)
		roots = navbar_manager.get_menu_editor_data()["menu"]
		linked_at_root = {item_group for root in roots for item_group in root["item_groups"]}
		top_level = set(
			frappe.get_all(
				"Item Group", filters={"parent_item_group": get_root_of("Item Group")}, pluck="name"
			)
		)
		self.assertEqual(top_level - linked_at_root, set(), "a top-level Item Group was not imported")
		self.assert_nested_set_valid("after a no-argument import")

	def test_import_is_idempotent_and_stops_at_the_depth_cap(self):
		navbar_manager.import_from_item_group(item_group=self.catalog)
		first_pass = sorted(frappe.get_all("Ecommerce Category", pluck="name"))

		navbar_manager.import_from_item_group(item_group=self.catalog)

		self.assertEqual(first_pass, sorted(frappe.get_all("Ecommerce Category", pluck="name")))
		self.assertEqual(
			labels_in_order([find_node(navbar_manager.get_menu_editor_data()["menu"], self.catalog)]),
			# The catalog's own order, not alphabetical: Clothing was created before Bags.
			[
				f"{PREFIX} Catalog {self.tag}",
				f"{PREFIX} Catalog {self.tag} > {PREFIX} Clothing {self.tag}",
				f"{PREFIX} Catalog {self.tag} > {PREFIX} Clothing {self.tag} > {PREFIX} Shirts {self.tag}",
				f"{PREFIX} Catalog {self.tag} > {PREFIX} Bags {self.tag}",
			],
		)
		# The fourth catalog level is skipped rather than thrown, and never reaches the menu.
		self.assertFalse(frappe.db.exists("Ecommerce Category", {"display_name": self.too_deep}))
		self.assertFalse(frappe.db.exists(ITEM_GROUP_LINK_DOCTYPE, {"item_group": self.too_deep}))
		self.assert_nested_set_valid("after a repeated import")

	def test_import_leaves_bounds_a_rebuild_would_not_change(self):
		navbar_manager.import_from_item_group(item_group=self.catalog)

		before = frappe.get_all(
			"Ecommerce Category", fields=["name", "lft", "rgt"], order_by="name asc", limit_page_length=0
		)
		rebuild_tree("Ecommerce Category")
		after = frappe.get_all(
			"Ecommerce Category", fields=["name", "lft", "rgt"], order_by="name asc", limit_page_length=0
		)
		self.assertEqual(before, after, "import left bounds a rebuild had to correct")

	def test_import_is_a_one_way_copy(self):
		"""Editing what the import produced must not reach back into the Item Group it came from."""
		navbar_manager.import_from_item_group(item_group=self.catalog)
		imported = find_node(navbar_manager.get_menu_editor_data()["menu"], self.catalog)
		column = next(child for child in imported["children"] if not child["children"])["name"]

		before = self.master_data_snapshot()

		navbar_manager.update_node(column, display_name="Renamed After Import")
		navbar_manager.move_node(column, None, 0)
		navbar_manager.set_visibility(column, 0)
		navbar_manager.delete_node(column)

		self.assert_master_data_untouched(before)
		self.assert_nested_set_valid("after editing an imported branch")

	def test_a_menu_import_leaves_the_erpnext_account_tree_intact(self):
		"""Regression: the import held core's request-global ``ignore_update_nsm``, which ERPNext's
		Account reads, so an Account written mid-import landed with stale lft/rgt."""
		company = frappe.get_all("Company", limit=1, pluck="name")
		if not company:
			self.skipTest("no Company on this site")
		parent_account = frappe.get_all(
			"Account", filters={"company": company[0], "is_group": 1}, limit=1, pluck="name"
		)[0]
		account_name = f"{PREFIX} Account {self.tag}"
		self.addCleanup(rebuild_tree, "Account")
		self.addCleanup(frappe.db.delete, "Account", {"account_name": account_name})

		real_create_node = navbar_manager.create_node
		written = []

		def create_node_and_an_account(*args, **kwargs):
			node = real_create_node(*args, **kwargs)
			# Only on the first node, so the Account is written inside the import's try/finally.
			if not written:
				self.assertTrue(
					frappe.local.flags.ignore_ecommerce_category_nsm,
					"the import is not holding its own flag, so this test proves nothing",
				)
				self.assertFalse(
					frappe.local.flags.ignore_update_nsm,
					"the import is holding core's request-global flag, which ERPNext's Account reads",
				)
				written.append(
					frappe.get_doc(
						{
							"doctype": "Account",
							"account_name": account_name,
							"parent_account": parent_account,
							"company": company[0],
							"is_group": 0,
						}
					)
					.insert(ignore_permissions=True)
					.name
				)
			return node

		with patch.object(navbar_manager, "create_node", create_node_and_an_account):
			navbar_manager.import_from_item_group(item_group=self.catalog)

		self.assertTrue(written, "the import created no node, so no Account was written mid-import")
		account = frappe.db.get_value("Account", written[0], ["lft", "rgt"], as_dict=True)
		self.assertGreater(account.lft, 0, "the Account landed with no nested-set bounds")
		self.assertEqual(account.rgt, account.lft + 1)

		# And the rest of the chart is still a valid tree. Not a rebuild-is-a-no-op check: a rebuild sorts
		# siblings by name, so it moves a valid chart whose accounts were created out of name order.
		self.assertEqual(
			self.nested_set_problems("Account", "parent_account"),
			[],
			"the menu import corrupted the chart of accounts",
		)

	def test_deleting_a_freshly_imported_node_reclaims_its_bounds(self):
		"""Regression: the bulk insert left ``old_parent`` NULL, so NestedSet read the delete as a
		no-op and never closed the node's lft/rgt gap."""
		navbar_manager.import_from_item_group(item_group=self.catalog)
		imported = find_node(navbar_manager.get_menu_editor_data()["menu"], self.catalog)
		leaf = next(child for child in imported["children"] if not child["children"])["name"]

		navbar_manager.delete_node(leaf)

		self.assert_nested_set_valid("after deleting a freshly imported node")

	def test_dragging_a_freshly_imported_column_to_the_top_level_moves_its_bounds(self):
		"""Regression: with ``old_parent`` NULL, a move to the top level updated the parent field but
		left the node's bounds inside its old parent, so it stayed a descendant of it."""
		navbar_manager.import_from_item_group(item_group=self.catalog)
		imported = find_node(navbar_manager.get_menu_editor_data()["menu"], self.catalog)
		column = imported["children"][0]["name"]

		navbar_manager.move_node(column, None, 0)

		self.assertIsNone(frappe.db.get_value("Ecommerce Category", column, "parent_ecommerce_category"))
		self.assertNotIn(column, get_descendants_of("Ecommerce Category", self.catalog))
		self.assert_nested_set_valid("after dragging an imported column to the top level")

	def test_renaming_a_freshly_imported_node_does_not_move_it(self):
		"""Regression: the same NULL ``old_parent`` made a plain rename re-seat the node as its
		parent's last child."""
		navbar_manager.import_from_item_group(item_group=self.catalog)
		# Pick the sibling first by lft: any other may already be last, making the assertion vacuous.
		column = frappe.get_all(
			"Ecommerce Category",
			filters={"parent_ecommerce_category": self.catalog},
			order_by="lft asc",
			limit=1,
			pluck="name",
		)[0]
		before = frappe.db.get_value("Ecommerce Category", column, ["lft", "rgt"], as_dict=True)

		navbar_manager.update_node(column, display_name="Just A Rename")

		after = frappe.db.get_value("Ecommerce Category", column, ["lft", "rgt"], as_dict=True)
		self.assertEqual((before.lft, before.rgt), (after.lft, after.rgt))
		self.assert_nested_set_valid("after renaming an imported node")

	def test_delete_node_removes_the_row_and_its_item_group_link(self):
		men = self.add_node(None, f"{PREFIX} Men {self.tag}")
		bags = self.add_node(men, f"{PREFIX} Bags", "Item Group", [self.bags])
		self.assertEqual(get_item_groups_by_entry([bags]), {bags: [self.bags]})

		navbar_manager.delete_node(bags)

		self.assertFalse(frappe.db.exists("Ecommerce Category", bags))
		self.assertEqual(get_item_groups_by_entry([bags]), {})
		self.assertTrue(frappe.db.exists("Ecommerce Category", men), "the parent must survive")
		self.assert_nested_set_valid("after deleting a linked node")

	def test_delete_node_cascades_through_the_subtree_and_keeps_the_nested_set_valid(self):
		men = self.add_node(None, f"{PREFIX} Men {self.tag}")
		column = self.add_node(men, f"{PREFIX} Accessories")
		leaf = self.add_node(column, f"{PREFIX} Bags", "Item Group", [self.bags])
		women = self.add_node(None, f"{PREFIX} Women {self.tag}")
		kept_leaf = self.add_node(women, f"{PREFIX} Shirts", "Item Group", [self.shirts])

		navbar_manager.delete_node(men)

		for name in (men, column, leaf):
			self.assertFalse(frappe.db.exists("Ecommerce Category", name))
		self.assertTrue(frappe.db.exists("Ecommerce Category", kept_leaf), "an unrelated branch was cut")
		self.assert_nested_set_valid("after deleting a branch with grandchildren")

	def test_hiding_a_node_prunes_its_whole_branch_and_spares_its_siblings(self):
		"""A hidden entry must take its children and grandchildren with it, not promote them."""
		men = self.add_node(None, f"{PREFIX} Men {self.tag}")
		hidden_column = self.add_node(men, f"{PREFIX} Hidden Column")
		buried_leaf = self.add_node(hidden_column, f"{PREFIX} Buried Leaf", "Item Group", [self.bags])
		kept_column = self.add_node(men, f"{PREFIX} Kept Column")
		kept_leaf = self.add_node(kept_column, f"{PREFIX} Kept Leaf", "Item Group", [self.shirts])

		navbar_manager.set_visibility(hidden_column, 0)

		storefront = get_menu_tree(enabled_only=True)
		self.assertIsNone(find_node(storefront, hidden_column))
		self.assertIsNone(
			find_node(storefront, buried_leaf), "a grandchild was promoted out of a hidden branch"
		)
		self.assertEqual(
			labels_in_order([find_node(storefront, men)]),
			[
				f"{PREFIX} Men {self.tag}",
				f"{PREFIX} Men {self.tag} > {PREFIX} Kept Column",
				f"{PREFIX} Men {self.tag} > {PREFIX} Kept Column > {PREFIX} Kept Leaf",
			],
		)
		self.assertIsNotNone(find_node(storefront, kept_leaf))

		# The editor still sees the hidden branch, so it can be switched back on.
		editor = navbar_manager.get_menu_editor_data()["menu"]
		self.assertIsNotNone(find_node(editor, buried_leaf))
		self.assertFalse(find_node(editor, hidden_column)["visible"])

	def test_hiding_a_root_tab_takes_the_whole_tab_with_it(self):
		men = self.add_node(None, f"{PREFIX} Men {self.tag}")
		column = self.add_node(men, f"{PREFIX} Accessories")
		leaf = self.add_node(column, f"{PREFIX} Bags", "Item Group", [self.bags])
		women = self.add_node(None, f"{PREFIX} Women {self.tag}")

		navbar_manager.set_visibility(men, 0)

		storefront = get_menu_tree(enabled_only=True)
		self.assertEqual([find_node(storefront, name) for name in (men, column, leaf)], [None, None, None])
		self.assertIsNotNone(find_node(storefront, women), "an unrelated tab was pruned too")

	def test_the_depth_cap_holds_for_the_editor(self):
		men = self.add_node(None, f"{PREFIX} Men {self.tag}")
		column = self.add_node(men, f"{PREFIX} Accessories")
		self.add_node(column, f"{PREFIX} Bags")
		leaf = frappe.get_all(
			"Ecommerce Category", filters={"parent_ecommerce_category": column}, pluck="name"
		)[0]

		with self.assertRaises(frappe.ValidationError):
			navbar_manager.add_node(parent=leaf, display_name=f"{PREFIX} Level {MAX_MENU_DEPTH + 1}")
