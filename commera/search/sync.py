import frappe
from frappe.utils import create_batch

from commera.search.build import ensure_index_built
from commera.search.engine_cache import new_search_engine
from commera.search.price_seq import bump_price_seq_after_commit
from commera.search.record_builder import IN_CLAUSE_CHUNK_SIZE

PRODUCT_DOCTYPE = "Style Attribute Variant"


def on_update(doc, method=None):
	enqueue_upsert(doc.doctype, doc.name)


def after_rename(doc, method=None, old=None, new=None, merge=False):
	enqueue_upsert(doc.doctype, doc.name)


def on_trash(doc, method=None):
	enqueue_remove(doc.doctype, doc.name)


def skip_sync():
	"""Whether the per-doc sync events should stay quiet for this write."""
	return skip_batch_sync() or bool(frappe.flags.in_import)


def skip_batch_sync():
	"""Whether a requested batch sync should stay quiet. Blind to `in_import`: an importer mutes the
	per-doc events and re-syncs the whole set at the end, so honouring it here would swallow that."""
	return bool(frappe.flags.in_migrate or frappe.flags.in_install or frappe.flags.in_patch)


def enqueue_upsert(doctype, name):
	if skip_sync():
		return
	bump_if_priced(doctype)
	frappe.enqueue(
		"commera.search.sync.upsert_doc",
		queue="default",
		enqueue_after_commit=True,
		doctype=doctype,
		name=name,
	)


def enqueue_upsert_many(doctype, names):
	"""Re-sync a set of docs in one job: frappe.db.set_value never fires the doc event that keeps the
	index fresh. Chunked because the names ride in the RQ payload, which redis has to carry."""
	names = list(names)
	if skip_batch_sync() or not names:
		return
	bump_if_priced(doctype)
	for chunk in create_batch(names, IN_CLAUSE_CHUNK_SIZE):
		frappe.enqueue(
			"commera.search.sync.upsert_docs",
			queue="long",
			enqueue_after_commit=True,
			doctype=doctype,
			names=chunk,
		)


def enqueue_remove(doctype, name):
	if skip_sync():
		return
	bump_if_priced(doctype)
	frappe.enqueue(
		"commera.search.sync.remove_doc",
		queue="default",
		enqueue_after_commit=True,
		doctype=doctype,
		name=name,
	)


def bump_if_priced(doctype):
	"""A product's save or deletion can add or drop its price rows. Bump before queueing its job."""
	if doctype == PRODUCT_DOCTYPE:
		bump_price_seq_after_commit()


def upsert_doc(doctype, name):
	write_if_indexed(lambda engine: engine.index_doc(doctype, name))


def upsert_docs(doctype, names):
	if not new_search_engine().index_exists():
		# No index yet: patching is a no-op, so build it instead of waiting for the nightly job.
		ensure_index_built()
		return
	write_if_indexed(lambda engine: engine.index_docs(doctype, names))


def remove_doc(doctype, name):
	write_if_indexed(lambda engine: engine.remove_doc(doctype, name))


def write_if_indexed(write):
	"""Run an index write once the index is built. Stamped price writes need no lock (price_seq); a
	failure raises, so RQ records the job as failed."""
	engine = new_search_engine()
	if engine.index_exists():
		write(engine)
