"""The single-writer lock of the search index. Every write reads the database after it takes the lock,
so no write lands an older read over a newer one."""

import frappe
from redis.exceptions import LockError

LOCK_KEY = "commera_search_index_write"
LOCK_TIMEOUT = 30
LOCK_BLOCKING_TIMEOUT = 10


def locked_index_write(write, timeout=LOCK_TIMEOUT, blocking_timeout=LOCK_BLOCKING_TIMEOUT):
	"""Run `write` under the lock, from a read snapshot taken after the lock. Skipped on a timeout."""
	try:
		with frappe.cache.lock(LOCK_KEY, timeout=timeout, blocking_timeout=blocking_timeout):
			refresh_snapshot()
			write()
	except LockError:
		frappe.log_error(
			title="Search index sync lock timeout",
			message=(
				f"Could not acquire '{LOCK_KEY}' within {blocking_timeout}s; skipping this "
				"index write. The next nightly rebuild will reconcile it."
			),
		)


def refresh_snapshot():
	"""Start a new read snapshot: REPEATABLE READ serves a transaction's reads from its first read."""
	# Tests share one transaction, and a commit would keep their rows.
	if not frappe.flags.in_test:
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
