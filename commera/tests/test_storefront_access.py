import frappe
from frappe.core.doctype.user_permission.test_user_permission import create_user
from frappe.tests import IntegrationTestCase
from frappe.utils import set_request
from frappe.website.serve import get_response

from commera.api.admin.home import get_home, set_storefront_published
from commera.patches import publish_existing_storefronts
from commera.roles import COMMERA_ADMIN
from commera.storefront_access import is_storefront_path, is_storefront_published
from commera.tests.test_localization import use_storefront_languages

STORE_ADMIN = "storefront-access-admin@example.com"
SYSTEM_MANAGER = "storefront-access-manager@example.com"
SHOPPER = "storefront-access-shopper@example.com"


def set_published(published: int):
	frappe.db.set_single_value("Commera Settings", "storefront_published", published)


class TestStorefrontAccess(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		# A Single's cached copy outlives the rollback unless it is cleared too.
		self.addCleanup(frappe.clear_document_cache, "Commera Settings", "Commera Settings")
		# Registered last so it runs first: the users below are rolled back with everything else.
		self.addCleanup(frappe.db.rollback)
		create_user(STORE_ADMIN, COMMERA_ADMIN)
		create_user(SYSTEM_MANAGER, "System Manager")
		create_user(SHOPPER, "Customer")
		frappe.db.set_value("User", SHOPPER, "user_type", "Website User")

	def get_status(self, user: str, path: str) -> int:
		frappe.set_user(user)
		set_request(method="GET", path=path)
		return get_response().status_code

	def test_only_storefront_paths_are_gated(self):
		use_storefront_languages(self, "en", published=("en", "ar"), unpublished=("fr",))
		for path in (
			"/",
			"/fr/products",
			"/en",
			"/en/products",
			"/ar/cart",
			"/cart/ITEM-1",
			"/index",
			"/account/dashboard",
			"/storefront-cart",
			"/sitemap.xml",
			"/sitemap-product-1.xml",
			"/llms.txt",
		):
			with self.subTest(path=path):
				self.assertTrue(is_storefront_path(path))
		for path in ("/commera", "/login", "/app/item", "/api/method/ping", "/files/a.png", "/de/products"):
			with self.subTest(path=path):
				self.assertFalse(is_storefront_path(path))

	def test_a_private_store_shows_visitors_the_coming_soon_page(self):
		set_published(0)
		for user in ("Guest", SHOPPER):
			with self.subTest(user=user):
				self.assertEqual(self.get_status(user, "/en"), 503)

	def test_staff_see_a_private_store(self):
		set_published(0)
		self.assertNotEqual(self.get_status(STORE_ADMIN, "/en"), 503)

	def test_login_stays_open_on_a_private_store(self):
		set_published(0)
		self.assertEqual(self.get_status("Guest", "/login"), 200)

	def test_a_published_store_is_open_to_visitors(self):
		set_published(1)
		self.assertNotEqual(self.get_status("Guest", "/en"), 503)

	def test_a_system_manager_publishes_and_unpublishes_the_store(self):
		set_published(0)
		frappe.set_user(SYSTEM_MANAGER)

		self.assertEqual(set_storefront_published(1), {"published": True})
		self.assertTrue(is_storefront_published())
		self.assertTrue(get_home()["published"])

		set_storefront_published(0)
		self.assertFalse(is_storefront_published())

	def test_a_commera_admin_reads_home_but_cannot_publish(self):
		frappe.set_user(STORE_ADMIN)

		self.assertFalse(get_home()["can_publish"])
		self.assertRaises(frappe.PermissionError, set_storefront_published, 1)

	def test_only_a_theme_editor_may_capture_the_store_preview(self):
		frappe.set_user(STORE_ADMIN)
		self.assertFalse(get_home()["preview"]["can_capture"])

	def test_home_reports_every_setup_task(self):
		self.assertEqual(set(get_home()["tasks"]), {"products", "payments", "shipping", "brand"})

	def test_a_store_that_was_already_set_up_stays_published_after_the_upgrade(self):
		set_published(0)
		publish_existing_storefronts.execute()
		self.assertEqual(is_storefront_published(), frappe.is_setup_complete())
