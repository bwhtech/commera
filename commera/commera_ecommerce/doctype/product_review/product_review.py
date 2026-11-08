# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import hashlib
from functools import partial

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.background_jobs import get_job_status
from frappe.utils.data import cint
from rq.job import JobStatus

from commera.api.reviews import get_rating_summary


class ProductReview(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		comment: DF.Text | None
		is_published: DF.Check
		item_style: DF.Link
		purchased_item: DF.Link | None
		rating: DF.Int
		replied_by: DF.Link | None
		replied_on: DF.Datetime | None
		review_title: DF.Data | None
		sales_order: DF.Link | None
		seller_reply: DF.Text | None
		variant: DF.Link
		verified_purchase: DF.Check
	# end: auto-generated types

	def autoname(self):
		# Deterministic and PII-free: a plain {variant}-{owner} name leaks reviewer emails to any
		# guest reading get_reviews, and risks overflowing the 140-char name limit.
		digest = hashlib.sha256(f"{self.variant}:{self.owner}".encode()).hexdigest()
		self.name = digest[:16]

	def validate(self):
		if not 1 <= cint(self.rating) <= 5:
			frappe.throw(_("Rating must be between 1 and 5"))

	def on_update(self):
		previous_doc = self.get_doc_before_save()
		previous_published = cint(previous_doc.is_published) if previous_doc else 0
		published_now = cint(self.is_published)
		rating_changed_while_published = (
			published_now and previous_doc and cint(previous_doc.rating) != cint(self.rating)
		)
		if previous_published != published_now or rating_changed_while_published:
			recompute_variant_rating(self.variant)

	def on_trash(self):
		if cint(self.is_published):
			recompute_variant_rating(self.variant)


def recompute_variant_rating(variant: str) -> None:
	"""Published-only aggregate for the variant's storefront summary. Called from this controller on
	publish/unpublish/delete instead of a scheduled sweep, so the numbers are never stale."""
	write_variant_rating(variant)
	# Two reviews saved at once each count without the other; a fresh read after both commit fixes it.
	frappe.db.after_commit.add(partial(queue_variant_rating, variant))


def write_variant_rating(variant: str) -> None:
	summary = get_rating_summary(variant)
	frappe.db.set_value(
		"Style Attribute Variant",
		variant,
		{"average_rating": summary["average_rating"], "review_count": summary["review_count"]},
		update_modified=False,
	)


def queue_variant_rating(variant: str) -> None:
	job_id = f"commera-variant-rating::{variant}"
	try:
		# A started job may have counted already, so a second one queues behind it.
		started = get_job_status(job_id) == JobStatus.STARTED
		frappe.enqueue(
			"commera.commera_ecommerce.doctype.product_review.product_review.write_variant_rating",
			variant=variant,
			job_id=None if started else job_id,
			deduplicate=not started,
		)
	except Exception:
		# Runs after commit: a full queue must not fail the saved review or skip the other callbacks.
		frappe.log_error(
			title="Variant rating recompute not queued",
			reference_doctype="Style Attribute Variant",
			reference_name=variant,
		)
