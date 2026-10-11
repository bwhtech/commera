import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.data import cint, flt, getdate, today
from frappe.utils.nestedset import get_descendants_of

PRODUCT = "Product"
ORDER = "Order"


class DiscountCodeError(frappe.ValidationError):
	pass


class CommeraDiscount(Document):
	"""A discount code. Commera applies it on top of ERPNext's price, into the standard discount fields."""

	def autoname(self):
		self.code = get_code_name(self.code)
		self.name = self.code

	def validate(self):
		if self.value_type == "Percentage" and flt(self.value) > 100:
			frappe.throw(_("A percentage discount cannot be more than 100."))
		if self.valid_from and self.valid_upto and getdate(self.valid_from) > getdate(self.valid_upto):
			frappe.throw(_("Valid From must be on or before Valid Upto."))

	def validate_usable(self):
		if not self.enabled:
			frappe.throw(_("{0} is not active.").format(self.code), DiscountCodeError)
		if self.valid_from and getdate(self.valid_from) > getdate(today()):
			frappe.throw(_("{0} is not active yet.").format(self.code), DiscountCodeError)
		if self.valid_upto and getdate(self.valid_upto) < getdate(today()):
			frappe.throw(_("{0} has expired.").format(self.code), DiscountCodeError)
		if self.usage_limit and cint(self.times_used) >= cint(self.usage_limit):
			frappe.throw(_("{0} has been used up.").format(self.code), DiscountCodeError)

	def can_combine_with(self, other: "CommeraDiscount") -> bool:
		return self.is_combinable_with(other.discount_class) and other.is_combinable_with(self.discount_class)

	def is_combinable_with(self, discount_class: str) -> bool:
		return bool(self.combines_with_product if discount_class == PRODUCT else self.combines_with_order)

	def is_for_currency(self, currency: str) -> bool:
		return self.value_type == "Percentage" or self.currency == currency

	def is_for_line(self, item) -> bool:
		if self.minimum_quantity and flt(item.qty) < cint(self.minimum_quantity):
			return False
		if not self.targets:
			return True

		variant_of = frappe.get_cached_value("Item", item.item_code, "variant_of")
		for target in self.targets:
			if target.target_type == "Item" and target.target in (item.item_code, variant_of):
				return True
			if target.target_type == "Brand" and target.target == item.brand:
				return True
			if target.target_type == "Item Group" and item.item_group in get_item_group_tree(target.target):
				return True
		return False

	def get_unit_discount(self, rate: float) -> float:
		if self.value_type == "Percentage":
			return min(rate * flt(self.value) / 100, rate)
		return min(flt(self.value), rate)

	def get_order_discount(self, subtotal: float) -> float:
		if self.minimum_subtotal and subtotal < flt(self.minimum_subtotal):
			return 0.0
		if self.value_type == "Percentage":
			return subtotal * flt(self.value) / 100
		return flt(self.value)

	def count_use(self, change: int):
		"""Add `change` to the use count, under a row lock so two orders cannot both take the last use."""
		times_used = cint(frappe.db.get_value(self.doctype, self.name, "times_used", for_update=True))
		if change > 0 and self.usage_limit and times_used >= cint(self.usage_limit):
			frappe.throw(_("{0} has been used up.").format(self.code), DiscountCodeError)
		frappe.db.set_value(self.doctype, self.name, "times_used", max(times_used + change, 0))


def get_code_name(code: str) -> str:
	return (code or "").strip().upper()


def get_item_group_tree(item_group: str) -> set[str]:
	return {item_group, *get_descendants_of("Item Group", item_group)}
