from unittest.mock import patch

import frappe
from frappe.apps import get_default_path
from frappe.core.doctype.user_permission.test_user_permission import create_user
from frappe.permissions import setup_custom_perms
from frappe.tests import IntegrationTestCase
from frappe.utils import set_request
from frappe.website.serve import get_response

from commera.api.permission import has_app_permission
from commera.patches import add_commera_admin_to_item_writers, grant_commera_admin_translation_rights
from commera.roles import (
	ADMIN_PERMISSIONS,
	COMMERA_ADMIN,
	COMMERA_USER,
	add_admin_permission,
	add_commera_roles,
	save_commera_default_app,
)
from commera.tests.test_plugins import OTHER_APP, PluginTestCase, page
from commera.www import commera as dashboard

ADMIN = "roles-admin@example.com"
SYSTEM_MANAGER = "roles-system-manager@example.com"
PICKER = "roles-picker@example.com"
ITEM_WRITER = "roles-item-writer@example.com"
WEBSITE_USER = "roles-website-user@example.com"
PATCH_ITEM_WRITER = "roles-patch-item-writer@example.com"
PATCH_DISABLED_ITEM_WRITER = "roles-patch-disabled@example.com"
PATCH_WEBSITE_USER = "roles-patch-website-user@example.com"
PATCH_STOCK_USER = "roles-patch-stock-user@example.com"
GRANTED_ADMIN = "roles-granted-admin@example.com"
GRANTED_USER = "roles-granted-user@example.com"
LANDING_PICKER = "roles-landing-picker@example.com"
LANDING_ADMIN = "roles-landing-admin@example.com"
TRANSLATION_ROW = {"parent": "Content Translation", "role": COMMERA_ADMIN, "permlevel": 0}
ITEM_ROW = {"parent": "Item", "role": COMMERA_ADMIN, "permlevel": 0}


def get_other_role_rows(doctype):
	rows = frappe.get_all(
		"Custom DocPerm",
		filters={"parent": doctype, "role": ("!=", COMMERA_ADMIN)},
		fields=["role", "permlevel", "read", "write", "create", "delete", "if_owner"],
		order_by="role, permlevel",
	)
	return [dict(row) for row in rows]


def customize_permissions(doctype):
	"""Custom DocPerm rows with a Commera Admin row, as a merchant's Role Permission Manager edit leaves."""
	setup_custom_perms(doctype)
	add_admin_permission(doctype, ("read",))


def make_website_user(email: str, *roles: str):
	create_user(email, *roles)
	frappe.db.set_value("User", email, "user_type", "Website User")
	frappe.clear_cache(user=email)


class TestDashboardGate(PluginTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		create_user(ADMIN, COMMERA_ADMIN)
		create_user(SYSTEM_MANAGER, "System Manager")
		create_user(PICKER, COMMERA_USER, "Stock User")
		create_user(ITEM_WRITER, "Item Manager")
		make_website_user(WEBSITE_USER, COMMERA_USER)

	def get_boot(self, user: str) -> frappe._dict:
		with self.set_user(user), patch.object(frappe.db, "commit"):
			return dashboard.get_boot()

	def test_a_commera_admin_and_a_system_manager_get_in_as_admins(self):
		for user in (ADMIN, SYSTEM_MANAGER):
			with self.subTest(user=user):
				self.assertTrue(self.get_boot(user).is_admin)
				self.assertTrue(has_app_permission(user))

	def test_a_commera_user_gets_in_and_sees_only_the_pages_its_roles_allow(self):
		self.write_manifest([page("stock", label="Stock", requires="Stock Entry")])
		self.write_manifest([page("quotes", label="Quotes", requires="Quotation")], app=OTHER_APP)

		boot = self.get_boot(PICKER)

		self.assertFalse(boot.is_admin)
		self.assertEqual([entry["label"] for entry in boot.plugins["entries"]], ["Stock"])
		self.assertTrue(has_app_permission(PICKER))

	def test_a_commera_user_with_no_visible_page_still_gets_in(self):
		self.write_manifest([page("quotes", label="Quotes", requires="Quotation")])
		self.assertEqual(self.get_boot(PICKER).plugins["entries"], [])

	def test_an_item_writer_without_a_commera_role_is_refused(self):
		self.assertFalse(has_app_permission(ITEM_WRITER))
		with self.assertRaises(frappe.PermissionError):
			self.get_boot(ITEM_WRITER)

	def test_a_website_user_is_refused_even_with_a_commera_role(self):
		self.assertFalse(has_app_permission(WEBSITE_USER))
		with self.assertRaises(frappe.PermissionError):
			self.get_boot(WEBSITE_USER)


class TestCommeraRoles(IntegrationTestCase):
	def test_adding_the_roles_twice_changes_nothing(self):
		add_commera_roles()
		roles = frappe.get_all("Role", filters={"name": ["in", [COMMERA_ADMIN, COMMERA_USER]]}, pluck="name")
		admin_rows = {"role": COMMERA_ADMIN, "parent": ["in", list(ADMIN_PERMISSIONS)]}
		permissions = frappe.get_all("Custom DocPerm", filters=admin_rows, fields=["parent"])

		add_commera_roles()

		self.assertCountEqual(roles, [COMMERA_ADMIN, COMMERA_USER])
		self.assertEqual(frappe.get_all("Custom DocPerm", filters=admin_rows, fields=["parent"]), permissions)
		self.assertCountEqual([row.parent for row in permissions], ADMIN_PERMISSIONS)

	def test_a_migrate_never_grants_back_a_revoked_right(self):
		self.addCleanup(frappe.db.rollback)
		add_commera_roles()
		frappe.db.set_value("Custom DocPerm", ITEM_ROW, "delete", 0)

		add_commera_roles()

		self.assertEqual(frappe.db.get_value("Custom DocPerm", ITEM_ROW, ["read", "delete"]), (1, 0))

	def test_the_translation_rights_patch_sets_only_the_missing_rights(self):
		self.addCleanup(frappe.db.rollback)
		customize_permissions("Content Translation")
		frappe.db.set_value("Custom DocPerm", TRANSLATION_ROW, {"delete": 0, "export": 1, "if_owner": 1})
		other_roles = get_other_role_rows("Content Translation")

		for _run in range(2):
			grant_commera_admin_translation_rights.execute()

		row = frappe.db.get_value("Custom DocPerm", TRANSLATION_ROW, ["*"], as_dict=True)
		self.assertEqual([row[right] for right in ("read", "write", "create", "delete")], [1] * 4)
		self.assertEqual((row.export, row.if_owner, row.submit), (1, 1, 0))
		self.assertEqual(get_other_role_rows("Content Translation"), other_roles)

	def test_the_translation_rights_patch_adds_a_missing_row(self):
		self.addCleanup(frappe.db.rollback)
		customize_permissions("Theme Layout")
		frappe.db.delete("Custom DocPerm", {"parent": "Theme Layout", "role": COMMERA_ADMIN})

		grant_commera_admin_translation_rights.execute()

		key = {"parent": "Theme Layout", "role": COMMERA_ADMIN, "permlevel": 0}
		rights = frappe.db.get_value("Custom DocPerm", key, ["read", "write", "create", "delete"])
		self.assertEqual(rights, (1, 1, 1, 0))

	def test_the_translation_rights_patch_leaves_json_permissions_alone(self):
		self.addCleanup(frappe.db.rollback)
		frappe.db.delete("Custom DocPerm", {"parent": ["in", ["Content Translation", "Theme Layout"]]})

		grant_commera_admin_translation_rights.execute()

		self.assertFalse(
			frappe.db.exists("Custom DocPerm", {"parent": ["in", ["Content Translation", "Theme Layout"]]})
		)

	def test_a_commera_admin_can_write_items(self):
		add_commera_roles()
		create_user(GRANTED_ADMIN, COMMERA_ADMIN)
		create_user(GRANTED_USER, COMMERA_USER)
		self.assertTrue(frappe.has_permission("Item", "write", user=GRANTED_ADMIN))
		self.assertFalse(frappe.has_permission("Item", "write", user=GRANTED_USER))

	def test_the_patch_makes_every_enabled_desk_item_writer_an_admin(self):
		create_user(PATCH_ITEM_WRITER, "Item Manager")
		create_user(PATCH_DISABLED_ITEM_WRITER, "Item Manager")
		frappe.db.set_value("User", PATCH_DISABLED_ITEM_WRITER, "enabled", 0)
		make_website_user(PATCH_WEBSITE_USER, "Item Manager")
		create_user(PATCH_STOCK_USER, "Stock User")

		add_commera_admin_to_item_writers.execute()

		self.assertIn(COMMERA_ADMIN, frappe.get_roles(PATCH_ITEM_WRITER))
		for user in (PATCH_DISABLED_ITEM_WRITER, PATCH_WEBSITE_USER, PATCH_STOCK_USER):
			with self.subTest(user=user):
				self.assertNotIn(COMMERA_ADMIN, frappe.get_roles(user))


class TestCommeraUserLanding(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		add_commera_roles()
		create_user(LANDING_PICKER, COMMERA_USER, "Stock User")
		create_user(LANDING_ADMIN, COMMERA_ADMIN, COMMERA_USER)

	def get_desk_response(self, user: str, path: str):
		with self.set_user(user):
			set_request(method="GET", path=path)
			return get_response()

	def test_a_commera_user_lands_on_commera_after_login(self):
		save_commera_default_app(frappe._dict(user=LANDING_PICKER))

		self.assertEqual(frappe.db.get_value("User", LANDING_PICKER, "default_app"), "commera")
		with self.set_user(LANDING_PICKER):
			self.assertEqual(get_default_path(), "/commera")

	def test_login_leaves_an_admins_default_app_alone(self):
		save_commera_default_app(frappe._dict(user=LANDING_ADMIN))
		self.assertFalse(frappe.db.get_value("User", LANDING_ADMIN, "default_app"))

	def test_a_commera_user_is_sent_from_desk_to_commera(self):
		for path in ("/desk", "/desk/stock-entry"):
			with self.subTest(path=path):
				response = self.get_desk_response(LANDING_PICKER, path)
				self.assertEqual(response.status_code, 301)
				self.assertTrue(response.headers["Location"].endswith("/commera"))

	def test_an_admin_with_commera_user_keeps_desk(self):
		self.assertEqual(self.get_desk_response(LANDING_ADMIN, "/desk").status_code, 200)
