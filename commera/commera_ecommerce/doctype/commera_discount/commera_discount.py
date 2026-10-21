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
		if self.enabled and self.eligibility == "Customer Groups" and not self.customer_groups:
			frappe.throw(_("Choose at least one customer group, or let everyone use this discount."))

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
		if reason := self.get_unusable_reason():
			frappe.throw(reason, DiscountCodeError)

	def get_unusable_reason(self) -> str | None:
		messages = {
			"Disabled": _("{0} is not active."),
			"Scheduled": _("{0} is not active yet."),
			"Expired": _("{0} has expired."),
			"Used Up": _("{0} has been used up."),
		}
		return messages[self.status].format(self.title) if self.status in messages else None

	def can_combine_with(self, other: "CommeraDiscount") -> bool:
		return self.is_combinable_with(other.discount_class) and other.is_combinable_with(self.discount_class)

	def is_combinable_with(self, discount_class: str) -> bool:
		fieldname = {
			PRODUCT: "combines_with_product",
			ORDER: "combines_with_order",
			SHIPPING: "combines_with_shipping",
		}
		return bool(self.get(fieldname[discount_class]))

	def is_for_currency(self, cart) -> bool:
		"""A fixed amount in another currency is converted, so only a currency with no exchange rate is out."""
		return cart.get_exchange_rate(self.currency) > 0

	def get_money(self, amount: float, cart) -> float:
		return cart.convert(amount, self.currency)

	def get_budget_left(self, cart) -> float | None:
		budget_left = self.budget_left
		return None if budget_left is None else self.get_money(budget_left, cart)

	def get_unmet_condition(self, cart) -> str | None:
		"""Why this discount does not apply to the cart now, in the shopper's words; None when it does."""
		minimum_subtotal = self.get_money(self.minimum_subtotal, cart)
		if self.minimum_requirement == "Subtotal" and cart.subtotal < minimum_subtotal:
			return _("Add {0} more to use {1}.").format(
				frappe.format_value(
					minimum_subtotal - cart.subtotal, {"fieldtype": "Currency"}, currency=cart.currency
				),
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

	def gives_anything(self, cart) -> bool:
		"""Whether the discount would take anything off this cart. One that gives nothing must not take a
		place that another, combinable discount could use."""
		if self.discount_class == PRODUCT:
			return any(self.get_line_discounts(cart).values())
		if self.discount_class == ORDER:
			return self.get_order_discount(cart) > 0
		# Before a delivery option is chosen there is nothing to judge a shipping discount on.
		if not cart.delivery_option:
			return True
		return self.get_delivery_discount(cart.delivery_option, cart) > 0

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
			return cap_discounts(discounts, self.get_money(self.maximum_discount, cart))
		value = self.get_money(self.value, cart)
		if self.fixed_applies_to == "Each Item":
			return {item.idx: min(value, flt(item.rate)) * flt(item.qty) for item in lines}
		return spread_amount(value, {item.idx: flt(item.amount) for item in lines})

	def get_buy_x_get_y_discounts(self, cart) -> dict[int, float]:
		"""The cheapest units the customer gets are discounted; the units that earn them cannot also be them."""
		# Matched once per line: an item group match walks the group tree, and the loop below runs per unit.
		buy_lines = {item.idx for item in cart.items if self.is_for_line(item, cart, "Buys")}
		get_lines = {item.idx for item in cart.items if self.is_for_line(item, cart, "Gets")}
		units = sorted(
			(flt(item.rate), item.idx, item)
			for item in cart.items
			for _unit in range(cint(item.qty))
			if item.idx in buy_lines or item.idx in get_lines
		)
		discounts = {}
		applications = 0
		while not self.uses_per_order or applications < cint(self.uses_per_order):
			rewarded = take_units(units, cint(self.get_quantity), lambda item: item.idx in get_lines)
			if not rewarded or not self.take_buy_units(units, buy_lines, cart):
				break
			for rate, idx, _item in rewarded:
				discounts[idx] = discounts.get(idx, 0) + self.get_reward(rate, cart)
			applications += 1
		return discounts

	def take_buy_units(self, units: list, buy_lines: set[int], cart) -> bool:
		buys = [unit for unit in units if unit[1] in buy_lines]
		if self.buy_requirement == "Quantity":
			if len(buys) < cint(self.buy_value):
				return False
			for unit in buys[-cint(self.buy_value) :]:
				units.remove(unit)
			return True
		# An amount requirement is met once by everything bought; it does not repeat per order.
		if sum(unit[0] for unit in buys) < self.get_money(self.buy_value, cart):
			return False
		units.clear()
		return True

	def get_reward(self, rate: float, cart) -> float:
		if self.get_value_type == "Free":
			return rate
		if self.get_value_type == PERCENTAGE:
			return rate * flt(self.get_value) / 100
		return min(self.get_money(self.get_value, cart), rate)

	def get_order_discount(self, cart) -> float:
		subtotal = sum(
			flt(item.amount)
			for item in cart.items
			if not (self.exclude_sale_items and cart.is_on_sale(item.item_code))
		)
		value = self.get_tier_value(subtotal, cart) if self.tiered else flt(self.value)
		if value is None:
			return 0.0
		if self.value_type != PERCENTAGE:
			return min(self.get_money(value, cart), subtotal)
		discount = subtotal * value / 100
		maximum_discount = self.get_money(self.maximum_discount, cart)
		return min(discount, maximum_discount) if maximum_discount else discount

	def get_tier_value(self, subtotal: float, cart) -> float | None:
		reached = [tier for tier in self.tiers if subtotal >= self.get_money(tier.minimum_subtotal, cart)]
		return flt(max(reached, key=lambda tier: flt(tier.minimum_subtotal)).value) if reached else None

	def get_delivery_discount(self, option: dict, cart) -> float:
		titles = {line.strip() for line in (self.delivery_options or "").splitlines() if line.strip()}
		if titles and option["title"] not in titles:
			return 0.0
		amount = flt(option["amount"])
		maximum_shipping_rate = self.get_money(self.maximum_shipping_rate, cart)
		if maximum_shipping_rate and amount > maximum_shipping_rate:
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
