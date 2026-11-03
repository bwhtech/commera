from types import SimpleNamespace

from frappe.tests import IntegrationTestCase

from commera.api.shipping import get_cart_parcels


class TestCartParcels(IntegrationTestCase):
	def test_the_parcel_lists_each_cart_line(self):
		quotation = SimpleNamespace(
			items=[
				SimpleNamespace(item_code="_Test Printful Tee", item_name="Tee", qty=2, rate=25),
				SimpleNamespace(item_code="_Test Printful Mug", item_name="Mug", qty=1, rate=12.5),
			]
		)

		items = get_cart_parcels(quotation)[0]["items"]

		self.assertEqual(
			items,
			[
				{"description": "Tee", "sku": "_Test Printful Tee", "quantity": 2, "rate": 25.0},
				{"description": "Mug", "sku": "_Test Printful Mug", "quantity": 1, "rate": 12.5},
			],
		)
