import os
import sqlite3
import time
from contextlib import closing
from unittest.mock import patch

import frappe
from frappe.search.sqlite_search import SQLiteSearchIndexMissingError
from frappe.utils.background_jobs import execute_job

from commera.localization.content import SHOP_WIDE
from commera.search import price_seq, price_sync, sync
from commera.search.engine_cache import clear_search_engine
from commera.search.sqlite_product_search import SqliteProductSearch
from commera.search.test_search_prices import PRODUCT, SearchPriceTestCase, start_transaction
from commera.tests.test_market_prices import make_price_list

BUSY = sqlite3.OperationalError("database is locked")


class PriceJobTestCase(SearchPriceTestCase):
	"""Runs a change, commits it, and hands back the jobs it queued, unrun."""

	def commit_and_queue(self, change):
		callbacks, jobs = start_transaction(), []

		def enqueue(method, enqueue_after_commit=False, **kwargs):
			def queue():
				if isinstance(method, str) and method.startswith("commera.search.sync."):
					jobs.append((method, kwargs))

			if enqueue_after_commit:
				callbacks.add(queue)
			else:
				queue()

		with (
			patch.object(frappe.db, "after_commit", callbacks),
			patch.object(frappe, "enqueue", enqueue),
		):
			change()
			callbacks.run()
		return jobs

	def run_jobs(self, jobs):
		for method, kwargs in jobs:
			kwargs = {key: kwargs[key] for key in ("doctype", "name", "names") if key in kwargs}
			frappe.get_attr(method)(**kwargs)

	def queued_products(self, jobs):
		return sorted(name for method, kwargs in jobs for name in kwargs.get("names", []))

	def store_price(self, product):
		clear_search_engine()
		return self.cards([product]).get(product, {}).get("effective_price")

	def price_rows(self, product):
		rows = self.engine.sql(
			"SELECT market FROM search_price WHERE doc_id = ?", (f"{PRODUCT}:{product}",), read_only=True
		)
		return sorted(row["market"] for row in rows)


class TestPriceEventsReadTheCommittedLists(PriceJobTestCase):
	def setUp(self):
		super().setUp()
		self.flash = make_price_list("Store Flash", self.store_currency)

	def switch_store_sale_list(self):
		"""Another request switches the store to Store Flash and commits."""
		frappe.db.set_single_value("Commera Settings", "sale_price_list", self.flash)

	def test_an_import_price_in_a_list_switched_to_before_its_commit_reindexes(self):
		# Reviewer's schedule: the import saw list A, then another request committed the switch to B.
		before = price_seq.read_price_seq()

		def import_a_price():
			self.make_item_price(self.item_codes["OTHER"]["M"], self.flash, 40)
			self.switch_store_sale_list()

		jobs = self.commit_and_queue(import_a_price)
		self.assertEqual(self.queued_products(jobs), [self.other])
		self.assertGreater(price_seq.read_price_seq(), before)
		self.run_jobs(jobs)
		self.assertEqual(self.store_price(self.other), 40)

	def test_a_list_switch_committed_after_the_import_rebuilds_with_its_price(self):
		jobs = self.commit_and_queue(
			lambda: self.make_item_price(self.item_codes["OTHER"]["M"], self.flash, 40)
		)
		self.assertEqual(jobs, [])
		self.switch_store_sale_list()
		self.engine.refresh_prices()
		self.assertEqual(self.store_price(self.other), 40)

	def test_a_renamed_item_price_reindexes_its_products(self):
		name = frappe.db.get_value(
			"Item Price", {"item_code": self.item_codes["OTHER"]["M"], "price_list": self.market_sale}
		)
		doc = frappe.get_doc("Item Price", name)
		jobs = self.commit_and_queue(lambda: price_sync.on_item_price_rename(doc, "after_rename", name, name))
		self.assertEqual(self.queued_products(jobs), [self.other])

	def test_renaming_an_indexed_price_list_rebuilds_the_index(self):
		other_list = make_price_list("Unindexed", self.currency)
		for price_list, rebuilds in ((other_list, 0), (self.market_sale, 1)):
			doc = frappe.get_doc("Price List", price_list)
			with patch.object(price_sync, "enqueue_full_rebuild") as rebuild:
				self.commit_and_queue(
					lambda doc=doc: price_sync.on_price_list_rename(doc, "after_rename", "old", doc.name)
				)
			self.assertEqual(rebuild.call_count, rebuilds)


class TestLostPriceSequence(PriceJobTestCase):
	def ahead_of_the_clock(self):
		return time.time_ns() // 1000 + 10**12

	def lose_the_counter(self):
		frappe.cache.delete(frappe.cache.make_key(price_seq.SEQ_KEY))

	def reprice_other(self, rate):
		price = frappe.db.get_value(
			"Item Price", {"item_code": self.item_codes["OTHER"]["M"], "price_list": self.market_sale}
		)
		frappe.db.set_value("Item Price", price, "price_list_rate", rate)
		price_seq.bump_price_seq()
		sync.upsert_docs(PRODUCT, [self.other])

	def gulf_price(self):
		clear_search_engine()
		with self.in_market():
			return self.cards([self.other]).get(self.other, {}).get("effective_price")

	def test_a_lost_counter_restarts_above_product_stamps_ahead_of_the_clock(self):
		stamp = self.ahead_of_the_clock()
		prices = {f"{PRODUCT}:{self.other}": {SHOP_WIDE: {"effective_price": 1}}}
		self.engine.write_transaction(lambda cursor: self.engine.write_stamped_prices(cursor, stamp, prices))
		self.lose_the_counter()
		self.assertGreater(price_seq.read_price_seq(), stamp)
		self.reprice_other(210)
		self.assertEqual(self.gulf_price(), 210)

	def test_a_lost_counter_restarts_above_the_priced_markets_stamp(self):
		stamp = self.ahead_of_the_clock()
		self.engine.write_transaction(
			lambda cursor: self.engine.write_price_markets(cursor, stamp, {SHOP_WIDE: None})
		)
		self.lose_the_counter()
		self.assertGreater(price_seq.read_price_seq(), stamp)

	def test_a_lost_counter_restarts_above_a_build_in_progress(self):
		stamp = self.ahead_of_the_clock()
		path = self.engine._get_db_path(is_temp=True)
		self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
		with closing(sqlite3.connect(path)) as connection:
			connection.execute("CREATE TABLE search_price_stamp (doc_id TEXT, seq INTEGER)")
			connection.execute("CREATE TABLE search_price_market (market TEXT, seq INTEGER)")
			connection.execute("INSERT INTO search_price_stamp VALUES ('x', ?)", (stamp,))
			connection.commit()
		self.lose_the_counter()
		self.assertGreater(price_seq.read_price_seq(), stamp)

	def test_a_kept_counter_is_not_reseeded(self):
		before = price_seq.read_price_seq()
		with patch.object(price_seq, "stored_seq", side_effect=AssertionError("reseeded")):
			self.assertEqual(price_seq.read_price_seq(), before)


class TestBusyIndexRetries(PriceJobTestCase):
	def reprice_other(self, rate):
		price = frappe.db.get_value(
			"Item Price", {"item_code": self.item_codes["OTHER"]["M"], "price_list": self.market_sale}
		)
		frappe.db.set_value("Item Price", price, "price_list_rate", rate)

	def gulf_price(self):
		clear_search_engine()
		with self.in_market():
			return self.cards([self.other]).get(self.other, {}).get("effective_price")

	def test_a_busy_index_asks_for_a_retry(self):
		for error in (BUSY, wrapped(BUSY), sqlite3.OperationalError("database table is locked")):
			with patch.object(SqliteProductSearch, "index_docs", side_effect=error):
				with self.assertRaises(frappe.RetryBackgroundJobError):
					sync.upsert_docs(PRODUCT, [self.other])

	def test_other_index_errors_raise_as_they_are(self):
		error = sqlite3.OperationalError("no such column: seq")
		with patch.object(SqliteProductSearch, "index_docs", side_effect=error):
			with self.assertRaises(sqlite3.OperationalError):
				sync.upsert_docs(PRODUCT, [self.other])

	def test_the_retry_reruns_the_whole_read_and_write(self):
		# The first attempt read 260 and hit a busy index; 210 was saved before the retry.
		write, attempts = SqliteProductSearch._index_documents, []

		def busy_once(engine, documents, **kwargs):
			attempts.append(True)
			if len(attempts) == 1:
				self.reprice_other(210)
				raise BUSY
			write(engine, documents, **kwargs)

		with (
			patch.object(SqliteProductSearch, "_index_documents", busy_once),
			patch.object(frappe.db, "commit"),
			patch.object(frappe.db, "rollback"),
			patch("frappe.utils.background_jobs.time.sleep") as sleep,
		):
			kwargs = {"doctype": PRODUCT, "names": [self.other]}
			execute_job(
				frappe.local.site, "commera.search.sync.upsert_docs", None, "t", kwargs, is_async=False
			)
		self.assertEqual(len(attempts), 2)
		sleep.assert_called_once_with(1)
		self.assertEqual(self.gulf_price(), 210)


class TestDelayedRemoval(PriceJobTestCase):
	def test_a_delayed_delete_keeps_a_recreated_product(self):
		data, rows = frappe.get_doc(PRODUCT, self.other).as_dict(), self.price_rows(self.other)
		delete_jobs = self.commit_and_queue(
			lambda: frappe.delete_doc(PRODUCT, self.other, ignore_permissions=True, force=True)
		)
		self.assertEqual([method for method, kwargs in delete_jobs], ["commera.search.sync.remove_doc"])

		recreate_jobs = self.commit_and_queue(
			lambda: frappe.get_doc(data).insert(ignore_permissions=True, set_name=self.other)
		)
		self.run_jobs(recreate_jobs)
		self.run_jobs(delete_jobs)
		self.assertEqual(self.price_rows(self.other), rows)
		self.assertIn(self.other, self.grid())

	def test_a_delete_job_removes_a_product_that_stays_deleted(self):
		jobs = self.commit_and_queue(
			lambda: frappe.delete_doc(PRODUCT, self.other, ignore_permissions=True, force=True)
		)
		self.run_jobs(jobs)
		self.assertEqual(self.price_rows(self.other), [])
		self.assertNotIn(self.other, self.grid())


class TestBuildDeletionCleanup(PriceJobTestCase):
	def test_build_cleanup_keeps_a_product_recreated_during_the_build(self):
		started_at = frappe.utils.now_datetime()
		frappe.get_doc(
			{
				"doctype": "Deleted Document",
				"deleted_doctype": PRODUCT,
				"deleted_name": self.other,
				"data": "{}",
			}
		).db_insert()

		self.engine.remove_documents_deleted_during_build(PRODUCT, started_at)

		self.assertIn(self.other, self.grid())
		self.assertNotEqual(self.price_rows(self.other), [])


def wrapped(error):
	"""Core wraps a connection's busy error, as _get_connection does."""
	try:
		raise SQLiteSearchIndexMissingError(str(error)) from error
	except SQLiteSearchIndexMissingError as wrapper:
		return wrapper
