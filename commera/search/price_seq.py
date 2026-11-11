"""Each price event bumps SEQ_KEY after it commits. A writer reads it, then the DB, and stamps what it writes:
stamp N saw event N, no write replaces a higher stamp, so event N's own job (it reads >= N) always lands."""

import time
from dataclasses import dataclass

import frappe

from commera.localization.market_prices import MarketPrices
from commera.search.price_markets import fresh_price_markets

SEQ_KEY = "commera_search_price_seq"


@dataclass(frozen=True)
class PriceRead:
	"""The sequence a writer read, and the price lists it read after it, from a fresh snapshot."""

	seq: int
	price_markets: dict[str, MarketPrices]

	@classmethod
	def begin(cls) -> "PriceRead":
		seq = read_price_seq()
		refresh_snapshot()
		return cls(seq, fresh_price_markets())


def bump_price_seq_after_commit():
	"""Call it before the event queues its job: after-commit callbacks run in the order added."""
	frappe.db.after_commit.add(bump_price_seq)


def bump_price_seq():
	key = start_seq()
	frappe.cache.incr(key)


def read_price_seq() -> int:
	return int(frappe.cache.get(start_seq()))


def start_seq() -> str:
	"""The counter's key. A flushed or evicted counter restarts above the clock and every stored stamp:
	a stamp read from a clock that ran ahead, or from an earlier restart, would reject newer writes."""
	key = frappe.cache.make_key(SEQ_KEY)
	if frappe.cache.get(key) is None:
		frappe.cache.set(key, max(stored_seq(), time.time_ns() // 1000) + 1, nx=True)
	return key


def stored_seq() -> int:
	"""The highest stamp the SQLite index holds. The only engine that stores stamps."""
	# Imported here: the engine imports this module.
	from commera.search.sqlite_product_search import SqliteProductSearch

	return SqliteProductSearch().max_price_seq()


def refresh_snapshot():
	"""Start a new read snapshot: REPEATABLE READ serves a transaction's reads from its first read."""
	# Tests share one transaction, and a commit would keep their rows.
	if not frappe.flags.in_test:
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
