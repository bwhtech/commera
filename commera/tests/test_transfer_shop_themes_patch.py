from unittest.mock import patch

from frappe.tests import UnitTestCase

from commera.patches import transfer_shop_themes_to_commera


class TestTransferShopThemesToCommera(UnitTestCase):
	def test_moves_the_legacy_module_to_commera(self):
		with (
			patch.object(transfer_shop_themes_to_commera.frappe.db, "get_value", return_value="ls_shop"),
			patch.object(transfer_shop_themes_to_commera.frappe.db, "set_value") as set_value,
			patch.object(transfer_shop_themes_to_commera.frappe, "clear_document_cache") as clear_cache,
			patch.object(transfer_shop_themes_to_commera.frappe.cache, "delete_value") as clear_redis,
			patch.object(transfer_shop_themes_to_commera.frappe.client_cache, "delete_value") as clear_client,
			patch.object(transfer_shop_themes_to_commera.frappe, "setup_module_map") as setup_module_map,
		):
			transfer_shop_themes_to_commera.execute()

		set_value.assert_called_once_with(
			"Module Def", "Shop Themes", "app_name", "commera", update_modified=False
		)
		clear_cache.assert_called_once_with("Module Def", "Shop Themes")
		clear_redis.assert_called_once_with("app_modules")
		clear_client.assert_called_once_with("installed_app_modules")
		setup_module_map.assert_called_once_with()

	def test_leaves_a_current_or_missing_module_unchanged(self):
		for owner in ("commera", None):
			with (
				self.subTest(owner=owner),
				patch.object(transfer_shop_themes_to_commera.frappe.db, "get_value", return_value=owner),
				patch.object(transfer_shop_themes_to_commera.frappe.db, "set_value") as set_value,
			):
				transfer_shop_themes_to_commera.execute()

			set_value.assert_not_called()
