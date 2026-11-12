import frappe
from frappe import _


def validate(doc, method=None):
	"""A market's template stays usable. Carts in the market refuse an unusable one, and a paid order
	cannot be placed with a template disabled after the payment started."""
	disabling = doc.disabled and doc.has_value_changed("disabled")
	if not disabling and not doc.has_value_changed("company"):
		return
	if markets := frappe.get_all("Commera Market", {"tax_template": doc.name}, pluck="market_name"):
		frappe.throw(
			_("Markets {0} use this tax template. Choose another template for them first.").format(
				", ".join(markets)
			),
			title=_("Template In Use"),
		)
