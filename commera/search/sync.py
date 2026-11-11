import frappe
from frappe.utils import create_batch

from commera.search.build import ensure_index_built
from commera.search.engine_cache import new_search_engine
from commera.search.record_builder import IN_CLAUSE_CHUNK_SIZE
from commera.search.write_lock import locked_index_write


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
	frappe.enqueue(
		"commera.search.sync.remove_doc",
		queue="default",
		enqueue_after_commit=True,
		doctype=doctype,
		name=name,
	)


def upsert_doc(doctype, name):
	serialized_write(lambda engine: engine.index_doc(doctype, name))


def upsert_docs(doctype, names):
	if not new_search_engine().index_exists():
		# No index yet: patching is a no-op, so build it instead of waiting for the nightly job.
		ensure_index_built()
		return
	serialized_write(lambda engine: engine.index_docs(doctype, names))


def remove_doc(doctype, name):
	serialized_write(lambda engine: engine.remove_doc(doctype, name))


def serialized_write(write):
	"""Run an index write under the single-writer cache lock; no-op until the index has been built."""
	engine = new_search_engine()
	if engine.index_exists():
		locked_index_write(lambda: write(engine))
