import frappe
from frappe import _
from frappe.utils import cstr, now_datetime

from commera.shopify.importers.base import UPDATED, ResourceImporter
from commera.shopify.queries import SHOP_QUERY
from commera.utils import get_store_currency

# Commera Settings field -> how to read it from the Shopify shop. Only empty fields are filled, so
# an import never overwrites what the merchant already set in Commera.
STORE_FIELDS = {
	"store_name": lambda shop: shop.get("name"),
	"contact_email": lambda shop: shop.get("contactEmail") or shop.get("email"),
}


class StoreImporter(ResourceImporter):
	"""Shop name, contact details and currency."""

	resource = "Store"

	def fetch_records(self) -> list[dict]:
		return [self.client.execute(SHOP_QUERY)["shop"]]

	def get_title(self, record: dict) -> str:
		return record.get("name")

	def import_record(self, shop: dict) -> str:
		save_shop_details(self.settings, shop)

		store_currency = get_store_currency()
		if shop.get("currencyCode") and shop["currencyCode"] != store_currency:
			self.warn(
				shop,
				_(
					"Shopify sells in {0} and this store sells in {1}. Prices are imported as numbers, without conversion."
				).format(shop["currencyCode"], store_currency),
			)

		# db_set, not save: a full save checks payments and price lists, which a new store may not
		# have set up yet, and nothing in Commera Settings reacts to these fields.
		commera_settings = frappe.get_single("Commera Settings")
		empty_fields = {
			fieldname: value
			for fieldname, read in STORE_FIELDS.items()
			if (value := cstr(read(shop)).strip()) and not commera_settings.get(fieldname)
		}
		if empty_fields:
			commera_settings.db_set(empty_fields)
		return UPDATED


def save_shop_details(settings, shop: dict) -> None:
	settings.db_set(
		{
			"shop_name": shop.get("name"),
			"shop_currency": shop.get("currencyCode"),
			"primary_domain": (shop.get("primaryDomain") or {}).get("host"),
			"connected_on": now_datetime(),
		},
		update_modified=False,
	)
