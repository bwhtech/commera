"""Published Theme Layouts, cached per theme and page under a generation that each commit bumps.
The commit writes its layout there; readers only add a missing entry, so an old snapshot cannot win."""

import pickle
from functools import partial

import frappe

KEY_PREFIX = "commera:theme_layout:"
GENERATION_PREFIX = "commera:theme_layout_generation:"
# Entries of an old generation are never read again, so they only need to expire.
EXPIRES_IN_SEC = 60 * 60


def get_published_layouts(theme_names, page) -> dict:
	"""{theme: its parsed published layout, or None}, from the cache where it can be trusted."""
	if has_uncommitted_layouts():
		# This transaction's own rows are not committed: read them, and keep them out of the cache.
		return read_published_layouts(theme_names, page)
	keys = dict(zip(theme_names, get_cache_keys(theme_names, page), strict=True))
	cached = {name: frappe.cache.get_value(key) for name, key in keys.items()}
	if any(entry is None for entry in cached.values()):
		stored = read_published_layouts(theme_names, page)
		for name, key in keys.items():
			cached[name] = {"layout": stored[name]}
			add_entry(key, cached[name])
	return {name: entry["layout"] for name, entry in cached.items()}


def read_published_layouts(theme_names, page) -> dict:
	"""The stored live layouts, read past the cache, for a save that must not trust it."""
	stored = dict(
		frappe.get_all(
			"Theme Layout",
			filters={"theme": ("in", theme_names), "page": page},
			fields=["theme", "published_layout"],
			as_list=True,
		)
	)
	return {name: frappe.parse_json(stored[name]) if stored.get(name) else None for name in theme_names}


def cache_layout_on_commit(theme_name, page, published_layout):
	"""Keep this transaction's reads off the cache, and cache the layout once it commits."""
	frappe.local.commera_uncommitted_layouts = True
	frappe.db.after_commit.add(partial(publish_entry, theme_name, page, published_layout))
	frappe.db.after_commit.add(forget_uncommitted_layouts)
	frappe.db.after_rollback.add(forget_uncommitted_layouts)


def clear_layout_cache(theme_name, page):
	"""Start a new generation, so the next read loads the stored row."""
	frappe.cache.incr(get_generation_key(theme_name, page))


def get_cache_keys(theme_names, page) -> list[str]:
	generation_keys = [get_generation_key(name, page) for name in theme_names]
	generations = frappe.cache.mget(generation_keys) if generation_keys else []
	return [
		get_cache_key(name, page, int(generation or 0))
		for name, generation in zip(theme_names, generations, strict=True)
	]


def get_cache_key(theme_name, page, generation) -> str:
	return f"{KEY_PREFIX}{theme_name}:{page}:{generation}"


def get_generation_key(theme_name, page) -> bytes:
	return frappe.cache.make_key(f"{GENERATION_PREFIX}{theme_name}:{page}")


def publish_entry(theme_name, page, published_layout):
	generation = frappe.cache.incr(get_generation_key(theme_name, page))
	entry = {"layout": frappe.parse_json(published_layout) if published_layout else None}
	set_entry(get_cache_key(theme_name, page, generation), entry)


def add_entry(key, entry):
	"""Set unless present: a committed layout written under this generation wins."""
	set_entry(key, entry, only_if_missing=True)


def set_entry(key, entry, only_if_missing=False):
	redis_key = frappe.cache.make_key(key)
	serialized = pickle.dumps(entry, protocol=pickle.DEFAULT_PROTOCOL)
	# make_key scopes the key to the site; set_value has no NX.
	# nosemgrep: frappe-semgrep-rules.rules.frappe-cache-breaks-multitenancy
	if frappe.cache.set(redis_key, serialized, ex=EXPIRES_IN_SEC, nx=only_if_missing):
		frappe.local.cache[redis_key] = entry
	else:
		# The committed entry won: read it next time instead of the remembered miss.
		frappe.local.cache.pop(redis_key, None)


def has_uncommitted_layouts() -> bool:
	return getattr(frappe.local, "commera_uncommitted_layouts", False)


def forget_uncommitted_layouts():
	frappe.local.commera_uncommitted_layouts = False
