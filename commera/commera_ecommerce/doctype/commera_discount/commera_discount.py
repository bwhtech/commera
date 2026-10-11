import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.data import cint, flt, getdate, today
from frappe.utils.nestedset import get_descendants_of

PRODUCT = "Product"
ORDER = "Order"
SHIPPING = "Shipping"
CLASS_BY_TYPE = {
	"Amount Off Products": PRODUCT,
	"Buy X Get Y": PRODUCT,
	"Amount Off Order": ORDER,
	"Free Shipping": SHIPPING,
}
PERCENTAGE = "Percentage"


class DiscountCodeError(frappe.ValidationError):
	pass


class CommeraDiscount(Document):
	"""A discount's rules. Commera applies it on top of ERPNext's price, into the standard discount fields."""

	def validate(self):
		self.validate_values()
		if self.starts_on and self.ends_on and getdate(self.starts_on) > getdate(self.ends_on):
			frappe.throw(_("Starts On must be on or before Ends On."))
		self.tiers = sorted(self.tiers, key=lambda tier: flt(tier.minimum_subtotal))
		self.validate_targets()

	def validate_values(self):
		percentages = [self.shipping_percentage]
		if self.value_type == PERCENTAGE:
			percentages += [self.value, *(tier.value for tier in self.tiers)]
		if self.get_value_type == PERCENTAGE:
			percentages.append(self.get_value)
		if any(flt(percentage) > 100 for percentage in percentages):
			frappe.throw(_("A percentage cannot be more than 100."))

	def validate_targets(self):
		roles = {target.role for target in self.targets}
		if self.discount_type == "Buy X Get Y":
			if not {"Buys", "Gets"} <= roles or not flt(self.buy_value) or not cint(self.get_quantity):
				frappe.throw(_("Buy X Get Y needs what the customer buys, how much, and what they get."))
		elif roles & {"Buys", "Gets"}:
			frappe.throw(_("Buys and Gets rows are only for Buy X Get Y."))

	@property
	def discount_class(self) -> str:
		return CLASS_BY_TYPE[self.discount_type]

	@property
	def budget_left(self) -> float | None:
		return max(flt(self.budget) - flt(self.discount_given), 0) if flt(self.budget) else None

	@property
	def status(self) -> str:
		if not self.enabled:
			return "Disabled"
		if self.starts_on and getdate(self.starts_on) > getdate(today()):
			return "Scheduled"
		if self.ends_on and getdate(self.ends_on) < getdate(today()):
			return "Expired"
		if (self.usage_limit and cint(self.times_used) >= cint(self.usage_limit)) or self.budget_left == 0:
			return "Used Up"
		return "Active"

	def validate_usable(self):
		messages = {
			"Disabled": _("{0} is not active."),
			"Scheduled": _("{0} is not active yet."),
			"Expired": _("{0} has expired."),
			"Used Up": _("{0} has been used up."),
		}
		if self.status in messages:
			frappe.throw(messages[self.status].format(self.title), DiscountCodeError)

	def can_combine_with(self, other: "CommeraDiscount") -> bool:
		return self.is_combinable_with(other.discount_class) and other.is_combinable_with(self.discount_class)

	def is_combinable_with(self, discount_class: str) -> bool:
		fieldname = {
			PRODUCT: "combines_with_product",
			ORDER: "combines_with_order",
			SHIPPING: "combines_with_shipping",
		}
		return bool(self.get(fieldname[discount_class]))

	def is_for_currency(self, currency: str) -> bool:
		return not self.currency or self.currency == currency

	def get_unmet_condition(self, cart) -> str | None:
		"""Why this discount does not apply to the cart now, in the shopper's words; None when it does."""
		if self.minimum_requirement == "Subtotal" and cart.subtotal < flt(self.minimum_subtotal):
			return _("Add {0} more to use {1}.").format(
				frappe.format_value(flt(self.minimum_subtotal) - cart.subtotal, {"fieldtype": "Currency"}),
				self.title,
			)
		if self.minimum_requirement == "Quantity" and cart.quantity < cint(self.minimum_quantity):
			return _("{0} needs at least {1} items.").format(self.title, cint(self.minimum_quantity))
		if self.payment_condition == "Prepaid" and cart.payment_kind == "cod":
			return _("{0} is for prepaid orders only.").format(self.title)
		if self.payment_condition == "Cash On Delivery" and cart.payment_kind != "cod":
			return _("{0} is for cash on delivery orders only.").format(self.title)
		if self.eligibility == "Customer Groups" and not self.is_for_customer_group(cart.customer_group):
			return _("{0} is not available for your account.").format(self.title)
		return None

	def is_for_customer_group(self, customer_group: str | None) -> bool:
		if not customer_group:
			return False
		return any(
			customer_group == row.customer_group
			or customer_group in get_descendants_of("Customer Group", row.customer_group)
			for row in self.customer_groups
		)

	def is_for_line(self, item, cart, role: str = "Applies To") -> bool:
		if self.exclude_sale_items and cart.is_on_sale(item.item_code):
			return False
		if self.has_target_match(item, "Excluded"):
			return False
		if role == "Applies To" and self.applies_to == "All Products":
			return True
		return self.has_target_match(item, role)

	def has_target_match(self, item, role: str) -> bool:
		variant_of = frappe.get_cached_value("Item", item.item_code, "variant_of")
		for target in self.targets:
			if target.role != role:
				continue
			if target.target_type == "Item" and target.target in (item.item_code, variant_of):
				return True
			if target.target_type == "Brand" and target.target == item.brand:
				return True
			if target.target_type == "Item Group" and item.item_group in get_item_group_tree(target.target):
				return True
		return False

	def get_line_discounts(self, cart) -> dict[int, float]:
		"""The whole-line discount this product discount gives each eligible line, keyed by row idx: an
		unsaved preview's rows have no name yet."""
		if self.discount_type == "Buy X Get Y":
			return self.get_buy_x_get_y_discounts(cart)

		lines = [item for item in cart.items if self.is_for_line(item, cart)]
		if self.value_type == PERCENTAGE:
			discounts = {item.idx: flt(item.amount) * flt(self.value) / 100 for item in lines}
			return cap_discounts(discounts, flt(self.maximum_discount))
		if self.fixed_applies_to == "Each Item":
			return {item.idx: min(flt(self.value), flt(item.rate)) * flt(item.qty) for item in lines}
		return spread_amount(flt(self.value), {item.idx: flt(item.amount) for item in lines})

	def get_buy_x_get_y_discounts(self, cart) -> dict[int, float]:
		"""The cheapest units the customer gets are discounted; the units that earn them cannot also be them."""
		units = sorted(
			(flt(item.rate), item.idx, item)
			for item in cart.items
			for _unit in range(cint(item.qty))
			if self.is_for_line(item, cart, "Buys") or self.is_for_line(item, cart, "Gets")
		)
		discounts = {}
		applications = 0
		while not self.uses_per_order or applications < cint(self.uses_per_order):
			rewarded = take_units(
				units, cint(self.get_quantity), lambda item: self.is_for_line(item, cart, "Gets")
			)
			if not rewarded or not self.take_buy_units(units, cart):
				break
			for rate, idx, _item in rewarded:
				discounts[idx] = discounts.get(idx, 0) + self.get_reward(rate)
			applications += 1
		return discounts

	def take_buy_units(self, units: list, cart) -> bool:
		buys = [unit for unit in units if self.is_for_line(unit[2], cart, "Buys")]
		if self.buy_requirement == "Quantity":
			if len(buys) < cint(self.buy_value):
				return False
			for unit in buys[-cint(self.buy_value) :]:
				units.remove(unit)
			return True
		# An amount requirement is met once by everything bought; it does not repeat per order.
		if sum(unit[0] for unit in buys) < flt(self.buy_value):
			return False
		units.clear()
		return True

	def get_reward(self, rate: float) -> float:
		if self.get_value_type == "Free":
			return rate
		if self.get_value_type == PERCENTAGE:
			return rate * flt(self.get_value) / 100
		return min(flt(self.get_value), rate)

	def get_order_discount(self, cart) -> float:
		subtotal = sum(
			flt(item.amount)
			for item in cart.items
			if not (self.exclude_sale_items and cart.is_on_sale(item.item_code))
		)
		value = self.get_tier_value(subtotal) if self.tiered else flt(self.value)
		if value is None:
			return 0.0
		if self.value_type != PERCENTAGE:
			return min(value, subtotal)
		discount = subtotal * value / 100
		return min(discount, flt(self.maximum_discount)) if flt(self.maximum_discount) else discount

	def get_tier_value(self, subtotal: float) -> float | None:
		reached = [tier for tier in self.tiers if subtotal >= flt(tier.minimum_subtotal)]
		return flt(reached[-1].value) if reached else None

	def get_delivery_discount(self, option: dict) -> float:
		titles = {line.strip() for line in (self.delivery_options or "").splitlines() if line.strip()}
		if titles and option["title"] not in titles:
			return 0.0
		amount = flt(option["amount"])
		if flt(self.maximum_shipping_rate) and amount > flt(self.maximum_shipping_rate):
			return 0.0
		return amount * flt(self.shipping_percentage) / 100


def take_units(units: list, quantity: int, is_wanted) -> list:
	wanted = [unit for unit in units if is_wanted(unit[2])][:quantity]
	if len(wanted) < quantity:
		return []
	for unit in wanted:
		units.remove(unit)
	return wanted


def cap_discounts(discounts: dict[int, float], cap: float) -> dict[int, float]:
	total = sum(discounts.values())
	if not cap or total <= cap:
		return discounts
	return {name: amount * cap / total for name, amount in discounts.items()}


def spread_amount(amount: float, amounts: dict[int, float]) -> dict[int, float]:
	"""Share one amount over lines in proportion to their value, never more than the lines are worth."""
	total = sum(amounts.values())
	if not total:
		return {}
	amount = min(amount, total)
	return {name: amount * value / total for name, value in amounts.items()}


def get_item_group_tree(item_group: str) -> set[str]:
	return {item_group, *get_descendants_of("Item Group", item_group)}
