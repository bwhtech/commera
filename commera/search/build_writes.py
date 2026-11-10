"""Products written to the index while a full build runs. The build read them earlier and may
write their old rows over the new ones, so it rewrites them from fresh reads once it commits."""

import frappe
from frappe.utils import create_batch

from commera.utils import IN_CLAUSE_CHUNK_SIZE

PRODUCT_DOCTYPE = "Style Attribute Variant"
# Set while a full build is queued or running.
BUILD_KEY = "commera_search_build_running"
# The products written meanwhile. Core's catch-up misses them: a price save leaves `modified` as is.
BUILD_WRITES_KEY = "commera_search_build_writes"
# Longer than any build's job timeout.
BUILD_TRACKING_SECONDS = 3 * 60 * 60


def track_build_writes():
	"""A full build is queued or starts: note each product written from now until it reconciles."""
	frappe.cache.set(frappe.cache.make_key(BUILD_KEY), 1, ex=BUILD_TRACKING_SECONDS)


def note_build_writes(doctype, names):
	"""Note `names` for the running build to rewrite: it may have read them before this write."""
	names = list(names or ())
	if doctype != PRODUCT_DOCTYPE or not names or not frappe.cache.exists(BUILD_KEY):
		return
	frappe.cache.sadd(BUILD_WRITES_KEY, *names)
	frappe.cache.expire_key(BUILD_WRITES_KEY, BUILD_TRACKING_SECONDS)


def reconcile_build_writes():
	"""After a build commits: rewrite the products noted while it ran from fresh reads."""
	from commera.search.sync import serialized_write

	# After the commit, so the build's read snapshot cannot hide the newer prices.
	frappe.cache.delete_value(BUILD_KEY)
	names = sorted(name.decode() for name in frappe.cache.smembers(BUILD_WRITES_KEY))
	for chunk in create_batch(names, IN_CLAUSE_CHUNK_SIZE):
		# A skipped chunk stays noted for the next build.
		if serialized_write(lambda engine, chunk=chunk: engine.index_docs(PRODUCT_DOCTYPE, chunk)):
			frappe.cache.srem(BUILD_WRITES_KEY, *chunk)
