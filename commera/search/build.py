import frappe
from frappe.rate_limiter import rate_limit

from commera.search.engine_cache import new_search_engine


def enqueue_full_rebuild(deduplicate=False):
	"""Enqueue a full rebuild of the active engine's index. Returns the enqueue payload."""
	return new_search_engine().enqueue_full_rebuild(deduplicate=deduplicate)


@frappe.whitelist()
@rate_limit(limit=5, seconds=60 * 60)
def rebuild_index():
	"""Manual entry: enqueue a full rebuild, restricted to System Manager and rate-limited."""
	frappe.only_for("System Manager")
	# An enqueue can return an RQ Job, which the JSON response cannot serialise.
	enqueue_full_rebuild()


def rebuild_index_nightly():
	"""Nightly reconciler: full rebuild for bulk/related edits that bypass the per-doc sync events."""
	return enqueue_full_rebuild()


def ensure_index_built():
	"""Build the active engine's index when it is absent, or resume a build that died part-way through."""
	return new_search_engine().ensure_index_built()
