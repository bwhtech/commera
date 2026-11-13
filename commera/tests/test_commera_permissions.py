"""Commera's own doctypes, except Commera Settings, grant their roles in the doctype JSON. Custom DocPerm
rows replace all of a doctype's own DocPerm rows."""

import frappe
from frappe.core.doctype.user_permission.test_user_permission import create_user
from frappe.model.document import Document
from frappe.modules.utils import get_doc_path
from frappe.permissions import add_permission, setup_custom_perms
from frappe.tests import IntegrationTestCase

from commera.patches import drop_commera_custom_docperms
from commera.roles import ADMIN_PERMISSIONS, COMMERA_ADMIN, add_commera_roles

COMMERA_ADMIN_USER = "permissions-commera-admin@example.com"
WEBSITE_MANAGER = "permissions-website-manager@example.com"
RIGHTS = ("read", "write", "create", "delete")


class PermissionsTestCase(IntegrationTestCase):
	def setUp(self):
		self.changed_doctypes = set()
		# Cleanups run last in, first out: the caches are cleared after the rollback.
		self.addCleanup(self.clear_changed_doctypes)
		self.addCleanup(frappe.db.rollback)

	def clear_changed_doctypes(self):
		for doctype in self.changed_doctypes:
			frappe.clear_cache(doctype=doctype)

	def use_json_permissions(self, doctype: str):
		"""What a migrate does to the doctype's DocPerm rows, inside this test's transaction."""
		self.changed_doctypes.add(doctype)
		doc = frappe.get_doc("DocType", doctype)
		doc.set("permissions", read_json_permissions(doc))
		frappe.db.delete("DocPerm", {"parent": doctype})
		for row in doc.permissions:
			row.db_insert()
		frappe.clear_cache(doctype=doctype)

	def copy_permissions_as_commera_did(self, doctype: str):
		"""The old add_commera_roles: copy DocPerm to Custom DocPerm. The JSON's Commera Admin row
		stands in for the row it then added."""
		frappe.db.delete("Custom DocPerm", {"parent": doctype})
		self.use_json_permissions(doctype)
		setup_custom_perms(doctype)


class TestCommeraAdminRights(PermissionsTestCase):
	def setUp(self):
		super().setUp()
		create_user(COMMERA_ADMIN_USER, COMMERA_ADMIN)

	def test_a_commera_admin_reads_and_manages_markets_in_desk(self):
		self.use_json_permissions("Commera Market")

		self.assert_rights("Commera Market", RIGHTS)
		with self.set_user(COMMERA_ADMIN_USER):
			self.assertIsInstance(frappe.get_list("Commera Market", pluck="name"), list)

	def test_a_commera_admin_reads_commera_settings(self):
		add_commera_roles()

		self.assert_rights("Commera Settings", ("read",))

	def test_a_commera_admin_manages_translations_and_theme_text(self):
		for doctype, rights in (("Content Translation", RIGHTS), ("Theme Layout", RIGHTS[:3])):
			frappe.db.delete("Custom DocPerm", {"parent": doctype})
			self.use_json_permissions(doctype)
			self.assert_rights(doctype, rights)

	def assert_rights(self, doctype: str, rights: tuple[str, ...]):
		for right in rights:
			with self.subTest(doctype=doctype, right=right):
				self.assertTrue(frappe.has_permission(doctype, right, user=COMMERA_ADMIN_USER))


class TestCommeraCustomDocPerm(PermissionsTestCase):
	def test_admin_permissions_name_commera_settings_as_the_only_commera_doctype(self):
		commera_doctypes = [doctype for doctype in ADMIN_PERMISSIONS if get_app(doctype) == "commera"]
		self.assertEqual(commera_doctypes, ["Commera Settings"])

	def test_adding_the_roles_leaves_commera_doctypes_without_custom_docperm(self):
		frappe.db.delete("Custom DocPerm", {"parent": ["in", drop_commera_custom_docperms.COMMERA_DOCTYPES]})

		add_commera_roles()

		self.assertFalse(
			frappe.db.exists(
				"Custom DocPerm", {"parent": ["in", drop_commera_custom_docperms.COMMERA_DOCTYPES]}
			)
		)

	def test_the_patch_drops_rows_that_copy_the_doctype_permissions(self):
		for doctype in ("Content Translation", "Theme Layout"):
			self.copy_permissions_as_commera_did(doctype)

		drop_commera_custom_docperms.execute()

		for doctype in ("Content Translation", "Theme Layout"):
			with self.subTest(doctype=doctype):
				self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": doctype}))
				roles = {row.role for row in frappe.get_meta(doctype).permissions}
				self.assertIn(COMMERA_ADMIN, roles)

	def test_the_patch_keeps_commera_settings_rows(self):
		frappe.db.delete("Custom DocPerm", {"parent": "Commera Settings"})
		setup_custom_perms("Commera Settings")
		rows = get_custom_rows("Commera Settings")

		drop_commera_custom_docperms.execute()

		self.assertTrue(rows)
		self.assertEqual(get_custom_rows("Commera Settings"), rows)

	def test_the_patch_keeps_rows_a_merchant_changed(self):
		self.copy_permissions_as_commera_did("Content Translation")
		add_permission("Content Translation", "Sales User")
		self.copy_permissions_as_commera_did("Theme Layout")
		frappe.db.set_value("Custom DocPerm", {"parent": "Theme Layout", "role": COMMERA_ADMIN}, "delete", 1)
		before = {doctype: get_custom_rows(doctype) for doctype in ("Content Translation", "Theme Layout")}

		drop_commera_custom_docperms.execute()

		for doctype, rows in before.items():
			with self.subTest(doctype=doctype):
				self.assertEqual(get_custom_rows(doctype), rows)

	def test_a_role_added_to_the_doctype_json_applies_after_the_patch(self):
		self.copy_permissions_as_commera_did("Content Translation")
		drop_commera_custom_docperms.execute()
		create_user(WEBSITE_MANAGER, "Website Manager")

		# The next release adds a role to the JSON, and the migrate syncs it into DocPerm.
		add_docperm("Content Translation", "Website Manager")

		self.assertTrue(frappe.has_permission("Content Translation", "read", user=WEBSITE_MANAGER))


def read_json_permissions(doc: Document) -> list[dict]:
	path = get_doc_path(doc.module, "DocType", doc.name) / f"{frappe.scrub(doc.name)}.json"
	return frappe.get_file_json(path)["permissions"]


def add_docperm(doctype: str, role: str):
	row = frappe.get_doc("DocType", doctype).append("permissions", {"role": role, "read": 1})
	row.idx = 99
	row.db_insert()
	frappe.clear_cache(doctype=doctype)


def get_app(doctype: str) -> str:
	return frappe.db.get_value("Module Def", frappe.db.get_value("DocType", doctype, "module"), "app_name")


def get_custom_rows(doctype: str) -> list[dict]:
	return frappe.get_all(
		"Custom DocPerm",
		filters={"parent": doctype},
		fields=["role", "permlevel", *RIGHTS],
		order_by="role, permlevel",
	)
