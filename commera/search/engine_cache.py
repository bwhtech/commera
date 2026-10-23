"""Picks the active search engine and caches one instance per request for the read paths."""

import frappe

from commera.search.engine import SearchEngineBase
from commera.search.sqlite_product_search import SqliteProductSearch


def get_engine_class() -> type[SearchEngineBase]:
	"""The active engine class. Only the SQLite engine exists so far."""
	return SqliteProductSearch


def new_search_engine() -> SearchEngineBase:
	"""A fresh engine for write and build paths, so no memoized read state goes stale."""
	return get_engine_class()()


def get_search_engine() -> SearchEngineBase:
	engine = getattr(frappe.local, "commera_search_engine", None)
	if engine is None:
		engine = new_search_engine()
		frappe.local.commera_search_engine = engine
	return engine


def clear_search_engine():
	"""Drop the request-scoped engine; only tests need it because frappe.local persists across tests."""
	frappe.local.commera_search_engine = None
