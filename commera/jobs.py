import frappe
from frappe.utils import add_to_date, get_url, now_datetime

from commera.localization import StorefrontLanguages
from commera.notifications import get_back_in_stock_context, is_customer_email_enabled, send_customer_email


def send_product_back_in_stock_email(doc, method):
	ecommerce_warehouse = frappe.get_cached_value(
		"Commera Settings", "Commera Settings", "ecommerce_warehouse"
	)
	if doc.warehouse != ecommerce_warehouse:
		return
	# The jobs read the voucher, which a worker sees only after this transaction commits.
	if doc.voucher_type == "Stock Entry":
		frappe.enqueue(
			send_product_in_stock_email_stock_entry,
			enqueue_after_commit=True,
			doc=doc,
			warehouse=ecommerce_warehouse,
		)

	if doc.voucher_type == "Purchase Receipt":
		frappe.enqueue(
			send_product_in_stock_email_purchase_receipt,
			enqueue_after_commit=True,
			doc=doc,
			warehouse=ecommerce_warehouse,
		)

	if doc.voucher_type == "Stock Reconciliation":
		frappe.enqueue(
			send_product_in_stock_email_stock_reconciliation,
			enqueue_after_commit=True,
			doc=doc,
			warehouse=ecommerce_warehouse,
		)


def send_product_in_stock_email_stock_entry(doc, warehouse):
	voucher = frappe.get_doc("Stock Entry", doc.voucher_no)

	if not voucher.stock_entry_type == "Material Receipt":
		return

	for item in voucher.items:
		if not item.t_warehouse == warehouse:
			continue
		notify_users_if_item_in_stock(item.item_code)


def send_product_in_stock_email_purchase_receipt(doc, warehouse):
	voucher = frappe.get_doc("Purchase Receipt", doc.voucher_no)

	if not voucher.set_warehouse == warehouse:
		return

	for item in voucher.items:
		notify_users_if_item_in_stock(item.item_code)


def send_product_in_stock_email_stock_reconciliation(doc, warehouse):
	voucher = frappe.get_doc("Stock Reconciliation", doc.voucher_no)

	for item in voucher.items:
		if not item.warehouse == warehouse:
			continue
		notify_users_if_item_in_stock(item.item_code)


def notify_users_if_item_in_stock(item_code):
	if not is_customer_email_enabled("back_in_stock"):
		return
	color_size_item = frappe.get_all(
		"Color Size Item",
		{"item_code": item_code, "parenttype": "Style Attribute Variant"},
		limit=1,
		pluck="parent",
	)
	if not color_size_item:
		return
	style_attribute_variant = frappe.get_cached_doc(
		"Style Attribute Variant",
		color_size_item[0],
		fields=["route", "is_published", "display_name"],
	)
	if not style_attribute_variant.is_published:
		return
	user_subscriptions = frappe.get_all(
		"OOS Notify Subscription",
		filters={"item": item_code, "notified": False},
		pluck="user",
	)
	if not user_subscriptions:
		return

	context = get_back_in_stock_context(item_code, style_attribute_variant)
	subscribers = {
		user.name: user
		for user in frappe.get_all(
			"User", filters={"name": ("in", user_subscriptions)}, fields=["name", "first_name", "language"]
		)
	}
	languages = StorefrontLanguages.load()
	for user in user_subscriptions:
		# Claimed before sending: two stock updates for the same item run this at once, and only the job
		# that flips the flag sends the email.
		if not claim_oos_subscription(item_code, user):
			continue
		subscriber = subscribers.get(user) or frappe._dict()
		language = languages.find(subscriber.language) or languages.default
		try:
			send_customer_email(
				"back_in_stock",
				[user],
				{
					**context,
					"first_name": subscriber.first_name,
					"product_url": get_url(
						f"/{language.code.lower()}/products/{style_attribute_variant.route}"
					),
				},
				language=subscriber.language,
				now=True,
			)
		except Exception as e:
			set_oos_notified(item_code, user, notified=False)
			frappe.log_error(
				title="Error sending Item in stock email",
				message=e,
				reference_doctype="OOS Notify Subscription",
				reference_name=user,
			)


def claim_oos_subscription(item_code: str, user: str) -> bool:
	return set_oos_notified(item_code, user, notified=True)


def set_oos_notified(item_code: str, user: str, notified: bool) -> bool:
	subscription = frappe.qb.DocType("OOS Notify Subscription")
	(
		frappe.qb.update(subscription)
		.set(subscription.notified, int(notified))
		.where(
			(subscription.item == item_code)
			& (subscription.user == user)
			& (subscription.notified == int(not notified))
		)
	).run()
	# The update row-locks the subscription until this job commits, so a second job waits, then matches
	# nothing.
	return frappe.db._cursor.rowcount > 0


def delete_notified_oos():
	frappe.db.delete("OOS Notify Subscription", {"notified": True})


def delete_old_draft_quotations():
	cutoff_time = add_to_date(now_datetime(), hours=-6)

	old_drafts = frappe.get_all(
		"Quotation",
		filters={
			"docstatus": 0,
			"creation": ("<", cutoff_time),
			"order_type": "Shopping Cart",
		},
		pluck="name",
	)
	# A cart with a payment still open is where sync_pending_gateway_payments places the order: keep it
	# until that payment settles, however old the cart itself is.
	paying = set(
		frappe.get_all(
			"Gateway Payment Request",
			filters={"ref_doctype": "Quotation", "ref_docname": ("in", old_drafts), "status": "Pending"},
			pluck="ref_docname",
		)
		if old_drafts
		else ()
	)
	for quotation in old_drafts:
		if quotation in paying:
			continue
		try:
			frappe.delete_doc("Quotation", quotation)
		except Exception as e:
			frappe.log_error(title=frappe._("Error in deleting the quotation {0}: {1}").format(quotation, e))


def sync_pending_gateway_payments():
	"""Settle checkouts the shopper's browser never confirmed, so captured money always reaches an order."""
	# ponytail: a request older than the lookback is left to manual reconciliation. delete_old_draft_
	# quotations keeps the draft cart of a Pending request, so the order can still be placed from it.
	now = now_datetime()
	pending_requests = frappe.get_all(
		"Gateway Payment Request",
		filters={
			"status": "Pending",
			# Upper bound skips requests too new to have settled - the shopper is likely still on the gateway.
			"creation": ("between", [add_to_date(now, hours=-6), add_to_date(now, minutes=-10)]),
		},
		# Oldest money first: those are the requests closest to losing the draft cart they point at.
		order_by="creation asc",
		pluck="name",
	)

	for payment_request in pending_requests:
		# Savepoint, not a bare rollback: a full rollback would discard every order the sweep already placed.
		savepoint = f"sweep_{payment_request}"
		try:
			frappe.db.savepoint(savepoint)
			frappe.get_doc("Gateway Payment Request", payment_request).sync_status()
			frappe.db.commit()
		except Exception:
			frappe.db.rollback(save_point=savepoint)
			frappe.log_error(
				title="Pending gateway payment sweep failed",
				reference_doctype="Gateway Payment Request",
				reference_name=payment_request,
			)
			frappe.db.commit()
