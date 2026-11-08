import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder.functions import Avg, Count
from frappe.rate_limiter import rate_limit
from frappe.utils.data import cint, cstr, flt

from commera.api.admin.orders import is_webshop_order
from commera.order_access import get_shopper_order_condition

MAX_COMMENT_LENGTH = 2000
MAX_REVIEW_TITLE_LENGTH = 140
PAGE_LENGTH = 10
MAX_PAGE_LENGTH = 50


def find_qualifying_purchase(variant: str) -> dict | None:
	"""Keyed on the shopper's orders, never Customer — core.py:105 mints a new Customer whenever the
	Contact/Portal-User lookup misses, so a customer-keyed query under-reports."""
	sales_order = frappe.qb.DocType("Sales Order")
	sales_order_item = frappe.qb.DocType("Sales Order Item")
	color_size_item = frappe.qb.DocType("Color Size Item")

	rows = (
		frappe.qb.from_(sales_order)
		.join(sales_order_item)
		.on(sales_order_item.parent == sales_order.name)
		.join(color_size_item)
		.on(color_size_item.item_code == sales_order_item.item_code)
		.select(sales_order.name.as_("sales_order"), sales_order_item.item_code.as_("item_code"))
		.where(get_shopper_order_condition(frappe.session.user))
		.where(is_webshop_order(sales_order))
		.where(color_size_item.parenttype == "Style Attribute Variant")
		.where(color_size_item.parent == variant)
		.orderby(sales_order.creation, order=Order.desc)
		.limit(1)
	).run(as_dict=True)

	return rows[0] if rows else None


def get_rating_summary(variant: str) -> dict:
	"""Published-only average + count for one variant, in a single query."""
	product_review = frappe.qb.DocType("Product Review")
	rows = (
		frappe.qb.from_(product_review)
		.select(
			Count(product_review.name).as_("review_count"), Avg(product_review.rating).as_("average_rating")
		)
		.where(product_review.variant == variant)
		.where(product_review.is_published == 1)
	).run(as_dict=True)

	row = rows[0] if rows else None
	return {
		"review_count": cint(row.review_count) if row else 0,
		"average_rating": flt(row.average_rating) if row and row.average_rating else 0.0,
	}


def get_rating_histogram(variant: str) -> dict:
	"""Published-only 1-5 star counts for one variant, in a single query."""
	product_review = frappe.qb.DocType("Product Review")
	rows = (
		frappe.qb.from_(product_review)
		.select(product_review.rating, Count(product_review.name).as_("count"))
		.where(product_review.variant == variant)
		.where(product_review.is_published == 1)
		.groupby(product_review.rating)
	).run(as_dict=True)

	count_by_rating = {cint(row.rating): cint(row["count"]) for row in rows}
	return {rating: count_by_rating.get(rating, 0) for rating in range(1, 6)}


@frappe.whitelist()
@rate_limit(limit=10, seconds=60 * 60)
def submit_review(variant: str, rating: int, review_title: str | None = None, comment: str | None = None):
	"""Not buyer-gated on purpose — the Verified Purchase badge distinguishes a reviewer who actually
	ordered. Always lands unpublished."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Sign in to write a review"))

	if not frappe.db.exists("Style Attribute Variant", variant):
		frappe.throw(_("Product not found"))

	rating = cint(rating)
	if not 1 <= rating <= 5:
		frappe.throw(_("Rating must be between 1 and 5"))

	review_title = cstr(review_title).strip()[:MAX_REVIEW_TITLE_LENGTH]
	comment = cstr(comment).strip()
	if len(comment) > MAX_COMMENT_LENGTH:
		frappe.throw(_("Review is too long"))

	if frappe.db.exists("Product Review", {"variant": variant, "owner": frappe.session.user}):
		frappe.throw(_("You have already reviewed this product"))

	purchase = find_qualifying_purchase(variant)
	item_style = frappe.db.get_value("Style Attribute Variant", variant, "item_style")

	review = frappe.new_doc("Product Review")
	review.variant = variant
	review.item_style = item_style
	review.rating = rating
	review.review_title = review_title
	review.comment = comment
	review.verified_purchase = 1 if purchase else 0
	review.sales_order = purchase.sales_order if purchase else None
	review.purchased_item = purchase.item_code if purchase else None
	review.is_published = 0
	try:
		# Portal shoppers have no create permission on Product Review; the checks above are the gate.
		review.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		# The upfront exists() check is TOCTOU under concurrent submits; the primary-key collision
		# is the real guard, this just keeps the loser's error message friendly.
		frappe.throw(_("You have already reviewed this product"))

	return review.name


@frappe.whitelist()
@rate_limit(limit=10, seconds=60 * 60)
def update_review(name: str, rating: int, review_title: str | None = None, comment: str | None = None):
	"""Every edit goes back through moderation: an approved review that could be silently rewritten
	would put unvetted text straight on the storefront."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Sign in to edit your review"))

	if frappe.db.get_value("Product Review", name, "owner") != frappe.session.user:
		frappe.throw(_("Review not found"))

	rating = cint(rating)
	if not 1 <= rating <= 5:
		frappe.throw(_("Rating must be between 1 and 5"))

	review_title = cstr(review_title).strip()[:MAX_REVIEW_TITLE_LENGTH]
	comment = cstr(comment).strip()
	if len(comment) > MAX_COMMENT_LENGTH:
		frappe.throw(_("Review is too long"))

	review = frappe.get_doc("Product Review", name)
	review.rating = rating
	review.review_title = review_title
	review.comment = comment
	# verified_purchase/sales_order/purchased_item stay frozen at submission time, so a later
	# cancellation or return cannot strip a badge the merchant already vetted.
	review.is_published = 0
	# Portal shoppers have no write permission on Product Review; the owner check above is the gate.
	review.save(ignore_permissions=True)

	return get_reviews(review.variant)


def get_own_review(variant: str) -> dict | None:
	"""What the session's own review currently says, so the storefront can pre-fill its edit form."""
	row = frappe.db.get_value(
		"Product Review",
		{"variant": variant, "owner": frappe.session.user},
		["name", "rating", "review_title", "comment", "is_published"],
		as_dict=True,
	)
	if not row:
		return None

	return {
		"name": row.name,
		"rating": cint(row.rating),
		"review_title": row.review_title,
		"comment": row.comment,
		"is_published": bool(cint(row.is_published)),
	}


# Guest read is deliberate: a product page must show its reviews to signed-out shoppers, and only
# is_published rows and their aggregates ever leave here.
@frappe.whitelist(allow_guest=True)  # nosemgrep: frappe-semgrep-rules.rules.security.guest-whitelisted-method
def get_reviews(variant: str, start: int = 0, page_length: int = PAGE_LENGTH):
	"""Published reviews for the storefront, plus the summary, histogram and the session's own
	review/write state. One query per concern; reviewer names are batched, never fetched per row."""
	if not frappe.db.exists("Style Attribute Variant", variant):
		frappe.throw(_("Product not found"))

	filters = {"variant": variant, "is_published": 1}
	total = frappe.db.count("Product Review", filters)

	review_rows = frappe.get_all(
		"Product Review",
		filters=filters,
		fields=[
			"name",
			"owner",
			"rating",
			"review_title",
			"comment",
			"verified_purchase",
			"seller_reply",
			"replied_on",
			"replied_by",
			"creation",
		],
		order_by="creation desc",
		start=cint(start),
		page_length=min(cint(page_length) or PAGE_LENGTH, MAX_PAGE_LENGTH),
		ignore_permissions=True,
	)

	reviewer_emails = {row.owner for row in review_rows}
	full_name_by_email = (
		{
			row.name: row.full_name
			for row in frappe.get_all(
				"User", filters={"name": ["in", list(reviewer_emails)]}, fields=["name", "full_name"]
			)
		}
		if reviewer_emails
		else {}
	)

	reviews = [
		{
			"name": row.name,
			"reviewer": full_name_by_email.get(row.owner, row.owner),
			"rating": cint(row.rating),
			"review_title": row.review_title,
			"comment": row.comment,
			"verified_purchase": bool(cint(row.verified_purchase)),
			"seller_reply": row.seller_reply,
			"replied_on": row.replied_on,
			"replied_by": row.replied_by,
			"creation": row.creation,
		}
		for row in review_rows
	]

	summary = get_rating_summary(variant)
	signed_in = frappe.session.user != "Guest"
	own_review = get_own_review(variant) if signed_in else None

	return {
		"reviews": reviews,
		"total": total,
		"average_rating": summary["average_rating"],
		"review_count": summary["review_count"],
		"histogram": get_rating_histogram(variant),
		"my_review": own_review,
		"has_reviewed": bool(own_review),
		"can_review": signed_in and not own_review,
	}
