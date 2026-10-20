"""The Discounts screens: discount rules, their codes, a test cart and the pickers the editor needs."""

import frappe
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils.data import cint, cstr, flt, getdate, today

from commera.discounts.cart_context import get_cart_context
from commera.discounts.codes import add_code, generate_codes, normalize_code
from commera.discounts.preview import get_preview_quotation
from commera.discounts.selection import get_unmet_reason

DOCTYPE = "Commera Discount"
PAGE_LENGTH = 20
MAX_PAGE_LENGTH = 100
MAX_TEST_LINES = 20

EDITABLE_FIELDS = (
	"title",
	"method",
	"discount_type",
	"enabled",
	"starts_on",
	"ends_on",
	"value_type",
	"value",
	"maximum_discount",
	"fixed_applies_to",
	"currency",
	"tiered",
	"applies_to",
	"exclude_sale_items",
	"buy_requirement",
	"buy_value",
	"uses_per_order",
	"get_quantity",
	"get_value_type",
	"get_value",
	"delivery_options",
	"shipping_percentage",
	"maximum_shipping_rate",
	"minimum_requirement",
	"minimum_subtotal",
	"minimum_quantity",
	"payment_condition",
	"eligibility",
	"combines_with_product",
	"combines_with_order",
	"combines_with_shipping",
	"usage_limit",
	"once_per_customer",
	"budget",
	"campaign",
	"discount_account",
)
TABLES = {
	"tiers": ("minimum_subtotal", "value"),
	"targets": ("role", "target_type", "target"),
	"customer_groups": ("customer_group",),
}
LIST_FIELDS = (
	"name",
	"title",
	"method",
	"discount_type",
	"enabled",
	"starts_on",
	"ends_on",
	"value_type",
	"value",
	"maximum_discount",
	"tiered",
	"payment_condition",
	"eligibility",
	"once_per_customer",
	"usage_limit",
	"budget",
	"times_used",
	"discount_given",
	# What the list's one-line summary reads.
	"exclude_sale_items",
	"minimum_requirement",
	"minimum_subtotal",
	"minimum_quantity",
	"buy_requirement",
	"buy_value",
	"get_quantity",
	"get_value_type",
	"get_value",
	"shipping_percentage",
	"combines_with_product",
	"combines_with_order",
	"combines_with_shipping",
)


@frappe.whitelist()
def get_discounts(
	tab: str = "all", search: str | None = None, start: int = 0, page_length: int = PAGE_LENGTH
):
	"""The Discounts list. A tab narrows by the dates and switch a status is read from."""
	frappe.has_permission(DOCTYPE, ptype="read", throw=True)

	discount = frappe.qb.DocType(DOCTYPE)
	condition = get_tab_condition(discount, tab)
	if search:
		matching = frappe.get_all(
			"Commera Discount Code", filters={"code": ("like", f"%{cstr(search)}%")}, pluck="discount"
		)
		by_text = discount.title.like(f"%{cstr(search)}%")
		by_code = discount.name.isin(matching) if matching else None
		search_condition = by_text | by_code if by_code is not None else by_text
		condition = search_condition if condition is None else condition & search_condition

	query = frappe.qb.from_(discount).select(*(discount[field] for field in LIST_FIELDS))
	count = frappe.qb.from_(discount).select(Count(discount.name))
	if condition is not None:
		query, count = query.where(condition), count.where(condition)
	rows = (
		query.orderby(discount.creation, order=frappe.qb.desc)
		.limit(min(cint(page_length) or PAGE_LENGTH, MAX_PAGE_LENGTH))
		.offset(cint(start))
	).run(as_dict=True)

	names = [row.name for row in rows]
	codes = get_code_summaries(names)
	tiers = get_tiers(names)
	return {
		"discounts": [
			{**row, **codes.get(row.name, {}), "tiers": tiers.get(row.name, []), "status": get_status(row)}
			for row in rows
		],
		"total": count.run()[0][0],
	}


def get_tab_condition(discount, tab: str):
	day = getdate(today())
	if tab in ("active", "used_up"):
		started = discount.starts_on.isnull() | (discount.starts_on <= day)
		running = discount.ends_on.isnull() | (discount.ends_on >= day)
		used_up = ((discount.usage_limit > 0) & (discount.times_used >= discount.usage_limit)) | (
			(discount.budget > 0) & (discount.discount_given >= discount.budget)
		)
		live = (discount.enabled == 1) & started & running
		return live & used_up if tab == "used_up" else live & used_up.negate()
	if tab == "scheduled":
		return (discount.enabled == 1) & (discount.starts_on > day)
	if tab == "expired":
		return discount.ends_on < day
	if tab == "disabled":
		return discount.enabled == 0
	return None


def get_status(row) -> str:
	return frappe.get_doc({"doctype": DOCTYPE, **row}).status


def get_tiers(discounts: list[str]) -> dict[str, list[dict]]:
	tiers = {}
	if not discounts:
		return tiers
	for row in frappe.get_all(
		"Commera Discount Tier",
		filters={"parent": ("in", discounts), "parenttype": DOCTYPE},
		fields=["parent", "minimum_subtotal", "value"],
		order_by="idx asc",
	):
		tiers.setdefault(row.parent, []).append(
			{"minimum_subtotal": row.minimum_subtotal, "value": row.value}
		)
	return tiers


def get_code_summaries(discounts: list[str]) -> dict[str, dict]:
	if not discounts:
		return {}
	rows = frappe.get_all(
		"Commera Discount Code",
		filters={"discount": ("in", discounts)},
		fields=["discount", "code", "is_generated", "times_used"],
		order_by="creation asc",
	)
	summaries = {}
	for row in rows:
		summary = summaries.setdefault(
			row.discount, {"code": None, "generated_codes": 0, "generated_codes_used": 0}
		)
		if row.is_generated:
			summary["generated_codes"] += 1
			summary["generated_codes_used"] += 1 if row.times_used else 0
		elif not summary["code"]:
			summary["code"] = row.code
	return summaries


@frappe.whitelist()
def get_discount(name: str) -> dict:
	frappe.has_permission(DOCTYPE, ptype="read", throw=True)
	discount = frappe.get_doc(DOCTYPE, name)
	record = {field: discount.get(field) for field in EDITABLE_FIELDS}
	for table, fields in TABLES.items():
		record[table] = [{field: row.get(field) for field in fields} for row in discount.get(table)]
	return {
		"name": discount.name,
		**record,
		**get_code_summaries([discount.name]).get(
			discount.name, {"code": None, "generated_codes": 0, "generated_codes_used": 0}
		),
		"status": discount.status,
		"discount_class": discount.discount_class,
		"performance": {
			"orders": cint(discount.times_used),
			"discount_given": flt(discount.discount_given),
			"sales": flt(discount.sales),
			"budget_left": discount.budget_left,
		},
	}


@frappe.whitelist(methods=["POST"])
def save_discount(discount: dict | str) -> dict:
	"""Create or update a discount from the editor. A code discount's single code is kept in step."""
	values = frappe.parse_json(discount)
	name = values.get("name")
	frappe.has_permission(DOCTYPE, ptype="write" if name else "create", throw=True)

	doc = frappe.get_doc(DOCTYPE, name) if name else frappe.new_doc(DOCTYPE)
	doc.update({field: values[field] for field in EDITABLE_FIELDS if field in values})
	for table, fields in TABLES.items():
		if table in values:
			doc.set(table, [{field: row.get(field) for field in fields} for row in values[table]])
	if doc.method == "Code" and not doc.title:
		doc.title = normalize_code(values.get("code"))
	doc.save()

	if doc.method == "Code" and values.get("code"):
		set_single_code(doc.name, values["code"])
	return get_discount(doc.name)


def set_single_code(discount: str, code: str):
	"""Point the discount's typed code at `code`. An old code that was used is kept, so its orders still link."""
	code = normalize_code(code)
	current = frappe.get_all(
		"Commera Discount Code",
		filters={"discount": discount, "is_generated": 0},
		fields=["name", "times_used"],
	)
	if any(row.name == code for row in current):
		return
	add_code(discount, code)
	for row in current:
		if not row.times_used:
			frappe.delete_doc("Commera Discount Code", row.name, ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def delete_discount(name: str):
	frappe.has_permission(DOCTYPE, ptype="delete", throw=True)
	if frappe.db.exists("Commera Discount Use", {"discount": name}):
		frappe.throw(_("Orders used this discount, so it is kept for their records. Switch it off instead."))
	for code in frappe.get_all("Commera Discount Code", filters={"discount": name}, pluck="name"):
		frappe.delete_doc("Commera Discount Code", code, ignore_permissions=True)
	frappe.delete_doc(DOCTYPE, name)


@frappe.whitelist(methods=["POST"])
def create_codes(name: str, count: int, prefix: str | None = None) -> dict:
	frappe.has_permission(DOCTYPE, ptype="write", throw=True)
	codes = generate_codes(name, count, prefix or "")
	return {"created": len(codes)}


@frappe.whitelist()
def download_codes(name: str):
	"""The discount's generated codes as CSV, with whether each was used."""
	frappe.has_permission(DOCTYPE, ptype="read", throw=True)
	rows = frappe.get_all(
		"Commera Discount Code",
		filters={"discount": name, "is_generated": 1},
		fields=["code", "times_used"],
		order_by="creation asc",
	)
	frappe.response["filename"] = f"{name}-codes.csv"
	frappe.response["filecontent"] = "code,used\n" + "".join(
		f"{row.code},{cint(row.times_used)}\n" for row in rows
	)
	frappe.response["type"] = "download"


@frappe.whitelist(methods=["POST"])
def test_discount(
	discount: dict | str,
	lines: list | str,
	payment_kind: str = "prepaid",
	first_order: int = 0,
	customer: str | None = None,
) -> dict:
	"""Price a cart with an unsaved draft of the discount, the way checkout would price it. With a
	customer, their group and order history decide the customer rules instead of `first_order`."""
	frappe.has_permission(DOCTYPE, ptype="read", throw=True)
	if customer:
		frappe.has_permission("Customer", doc=customer, ptype="read", throw=True)
	values = frappe.parse_json(discount)
	lines = [
		{"item_code": cstr(line["item_code"]), "qty": max(cint(line.get("qty")), 1)}
		for line in (frappe.parse_json(lines) or [])[:MAX_TEST_LINES]
		if line.get("item_code")
	]
	if not lines:
		return {"lines": [], "subtotal": 0, "discount": 0, "total": 0, "reasons": []}

	draft = frappe.get_doc({"doctype": DOCTYPE, **{field: values.get(field) for field in EDITABLE_FIELDS}})
	for table, fields in TABLES.items():
		draft.set(table, [{field: row.get(field) for field in fields} for row in values.get(table) or []])
	# The test shows the rules' effect today, whatever the switch and dates say.
	draft.update(
		{"enabled": 1, "starts_on": None, "ends_on": None, "title": draft.title or _("This discount")}
	)
	flags = {
		"commera_discounts": [draft],
		"commera_payment_kind": "cod" if payment_kind == "cod" else "prepaid",
		"commera_first_order": None if customer else bool(cint(first_order)),
	}
	quotation = get_preview_quotation(
		lines, flags=flags, fields={"party_name": customer} if customer else None
	)
	subtotal = sum(flt(item.price_list_rate) * flt(item.qty) for item in quotation.items)
	return {
		"lines": [
			{
				"item_code": item.item_code,
				"title": item.item_name,
				"qty": flt(item.qty),
				"price": flt(item.price_list_rate),
				"discount": flt(item.custom_code_discount) * flt(item.qty),
				"amount": flt(item.amount),
			}
			for item in quotation.items
		],
		"subtotal": subtotal,
		"discount": subtotal - flt(quotation.net_total),
		"total": flt(quotation.net_total),
		"reasons": [reason] if (reason := get_unmet_reason(draft, get_cart_context(quotation))) else [],
	}


@frappe.whitelist()
def get_editor_options() -> dict:
	"""The choices the editor's pickers offer that do not need a search."""
	frappe.has_permission(DOCTYPE, ptype="read", throw=True)
	company = frappe.defaults.get_global_default("company")
	return {
		"currency": frappe.get_cached_value("Company", company, "default_currency") if company else None,
		"customer_groups": as_picker_options(
			frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", order_by="name")
		),
		"campaigns": frappe.get_all("UTM Campaign", pluck="name", order_by="name"),
		"discount_accounts": frappe.get_all(
			"Account",
			filters={"company": company, "is_group": 0, "disabled": 0},
			pluck="name",
			order_by="name",
			limit=500,
		),
		"delivery_options": as_picker_options(get_delivery_option_titles()),
	}


def as_picker_options(names: list[str]) -> list[dict]:
	return [{"label": name, "value": name} for name in names]


def get_delivery_option_titles() -> list[str]:
	if not frappe.db.exists("DocType", "Shipping Service"):
		return []
	return frappe.get_all("Shipping Service", filters={"enabled": 1}, pluck="title", order_by="title")


@frappe.whitelist()
def search_targets(target_type: str, search: str | None = None, sellable: int = 0) -> list[dict]:
	"""Products, collections or brands for a discount's target pickers. `sellable` lists the items a
	cart can hold, such as each size, rather than the products they belong to."""
	search = f"%{cstr(search)}%"
	if target_type == "Item":
		frappe.has_permission("Item", ptype="read", throw=True)
		rows = frappe.get_all(
			"Item",
			filters={"disabled": 0, "has_variants": 0}
			if cint(sellable)
			else {"disabled": 0, "variant_of": ("is", "not set")},
			or_filters={"name": ("like", search), "item_name": ("like", search)},
			fields=["name", "item_name"],
			order_by="item_name",
			limit=20,
		)
		return [{"label": row.item_name, "value": row.name} for row in rows]
	if target_type == "Item Group":
		frappe.has_permission("Item Group", ptype="read", throw=True)
		item_group = frappe.qb.DocType("Item Group")
		names = (
			frappe.qb.from_(item_group)
			.select(item_group.name)
			.where((item_group.rgt == item_group.lft + 1) & item_group.name.like(search))
			.orderby(item_group.name)
			.limit(20)
		).run(pluck=True)
		return [{"label": name, "value": name} for name in names]
	if target_type == "Customer":
		frappe.has_permission("Customer", ptype="read", throw=True)
		rows = frappe.get_list(
			"Customer",
			filters={"disabled": 0},
			or_filters={"name": ("like", search), "customer_name": ("like", search)},
			fields=["name", "customer_name", "customer_group"],
			order_by="customer_name",
			limit=20,
		)
		return [
			{"label": row.customer_name, "value": row.name, "description": row.customer_group} for row in rows
		]
	if target_type == "Brand":
		frappe.has_permission("Brand", ptype="read", throw=True)
		names = frappe.get_all(
			"Brand", filters={"name": ("like", search)}, pluck="name", order_by="name", limit=20
		)
		return [{"label": name, "value": name} for name in names]
	frappe.throw(_("Unknown target type {0}.").format(target_type))
