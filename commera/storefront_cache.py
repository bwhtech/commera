"""Epoch-versioned L1 (worker RAM) + L2 (Redis) cache for guest storefront APIs and SSR pages.
Mutations defer epoch bumps via after_commit so concurrent readers never cache uncommitted rows."""

from __future__ import annotations

import copy
import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

import frappe
from frappe.utils.response import json_handler
from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response

EPOCHS_HASH_KEY = "commera:sf_epochs"
ALL_DOMAINS = ("catalog", "prices", "stock", "discounts", "reviews", "shop", "theme", "party")
CATALOG_READ_DOMAINS = ("catalog", "prices", "stock", "discounts", "shop")
PDP_DOMAINS = ("catalog", "prices", "stock", "discounts", "reviews", "shop")
SHOP_DOMAINS = ("shop", "theme")

L1_MAX_ENTRIES = 1024
L1_SSR_MAX_ENTRIES = 256
MAX_SSR_CACHE_BYTES = 512 * 1024

# Paths that must never be served from the shared guest SSR page cache.
NON_CACHEABLE_SSR_PREFIXES = (
	"cart",
	"account",
	"checkout",
	"login",
	"signup",
	"storefront-cart",
	"storefront-login",
	"track-order",
	"og-image",
	"commera",
)
PREVIEW_QUERY_PARAMS = frozenset({"preview_theme", "preview", "editor", "edit", "theme_preview"})
# Only query parameters that change page output enter the SSR key; tracking params (utm_*, fbclid) share hits.
ALLOWED_SSR_QUERY_PARAMS = frozenset(
	{
		"category",
		"search",
		"sort_by",
		"page",
		"page_size",
		"brands",
		"colors",
		"sizes",
		"min",
		"max",
		"has_discount",
		"size",
		"_lang",
		"country",
	}
)

# Per-worker L1 LRU caches: key -> (expires_at, value)
_l1_api: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_l1_bytes: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
_l1_ssr: OrderedDict[str, tuple[float, bytes]] = OrderedDict()


class CachedStorefrontResponse(HTTPException):
	"""Raised in before_request on a verified guest SSR cache hit to bypass PathResolver/Jinja."""

	code = 200

	def __init__(self, response: Response):
		super().__init__()
		self._response = response

	def get_response(self, environ=None, scope=None) -> Response:
		return self._response


def is_cache_enabled() -> bool:
	"""Enabled everywhere except unit tests unless opted in via enable_storefront_cache_in_test."""
	if frappe.flags.in_test and not frappe.flags.get("enable_storefront_cache_in_test"):
		return False
	return True


def _site() -> str:
	return getattr(frappe.local, "site", "") or ""


def _dirty_domains() -> set[str]:
	return getattr(frappe.local, "_commera_sf_dirty_domains", None) or set()


def _is_domain_dirty(domains: tuple[str, ...]) -> bool:
	dirty = _dirty_domains()
	return bool(dirty and any(domain in dirty for domain in domains))


def _clear_local_memos(domains: tuple[str, ...]) -> None:
	if hasattr(frappe.local, "_commera_sf_epochs"):
		delattr(frappe.local, "_commera_sf_epochs")
	if "shop" in domains or "theme" in domains or "catalog" in domains:
		for attr in (
			"_commera_sf_languages",
			"_commera_sf_markets",
			"_commera_sf_markets_hidden",
			"commera_published_layouts_cache",
			"commera_storefront_menu",
		):
			if hasattr(frappe.local, attr):
				delattr(frappe.local, attr)


def _decode_redis_token(value: bytes | str) -> str:
	return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def get_epochs() -> dict[str, int]:
	"""Fetch all storefront cache domain epochs once per request (one Redis HGETALL)."""
	cached = getattr(frappe.local, "_commera_sf_epochs", None)
	if cached is not None:
		return cached
	raw = {}
	try:
		key = frappe.cache.make_key(EPOCHS_HASH_KEY)
		raw = frappe.cache.execute_command("HGETALL", key) or {}
		if isinstance(raw, list):
			raw = dict(zip(raw[0::2], raw[1::2], strict=False))
	except Exception:
		frappe.logger("commera.storefront_cache").exception("Failed to read storefront cache epochs")
		raw = {}
	decoded = {_decode_redis_token(k): _decode_redis_token(v) for k, v in raw.items()}
	epochs = {}
	for domain in ALL_DOMAINS:
		try:
			epochs[domain] = int(decoded.get(domain, 0))
		except (TypeError, ValueError):
			epochs[domain] = 0
	frappe.local._commera_sf_epochs = epochs
	return epochs


def epoch_stamp(domains: tuple[str, ...]) -> str:
	epochs = get_epochs()
	return ":".join(str(epochs.get(d, 0)) for d in domains)


def _flush_redis_epochs(domains: tuple[str, ...]) -> None:
	if not domains:
		return
	key = frappe.cache.make_key(EPOCHS_HASH_KEY)
	try:
		pipe = frappe.cache.pipeline()
		for domain in domains:
			pipe.hincrby(key, domain, 1)
		pipe.execute()
	except Exception:
		frappe.logger("commera.storefront_cache").exception(
			"Failed to bump storefront cache epochs: %s", ",".join(domains)
		)
	_clear_local_memos(domains)


def _flush_pending_commit_bumps() -> None:
	pending = getattr(frappe.local, "_commera_sf_pending_bumps", None)
	if pending:
		domains = tuple(sorted(pending))
		pending.clear()
		_flush_redis_epochs(domains)
	if hasattr(frappe.local, "_commera_sf_dirty_domains"):
		frappe.local._commera_sf_dirty_domains.clear()
	frappe.local._commera_sf_hooks_registered = False


def _clear_pending_rollback_bumps() -> None:
	if pending := getattr(frappe.local, "_commera_sf_pending_bumps", None):
		pending.clear()
	if dirty := getattr(frappe.local, "_commera_sf_dirty_domains", None):
		dirty.clear()
	frappe.local._commera_sf_hooks_registered = False
	_clear_local_memos(ALL_DOMAINS)


def bump_epochs(*domains: str, immediate: bool = False) -> None:
	"""Invalidate cache domains: immediately for clear_cache, or on after_commit for DB writes.
	Inside an active transaction, dirty domains bypass shared L1/L2 until commit or rollback."""
	target = domains or ALL_DOMAINS
	_clear_local_memos(target)

	if immediate or not getattr(frappe.local, "db", None):
		_flush_redis_epochs(target)
		return

	dirty = getattr(frappe.local, "_commera_sf_dirty_domains", None)
	if dirty is None:
		dirty = frappe.local._commera_sf_dirty_domains = set()
	dirty.update(target)

	pending = getattr(frappe.local, "_commera_sf_pending_bumps", None)
	if pending is None:
		pending = frappe.local._commera_sf_pending_bumps = set()
	pending.update(target)

	if not getattr(frappe.local, "_commera_sf_hooks_registered", False):
		frappe.local._commera_sf_hooks_registered = True
		frappe.db.after_commit.add(_flush_pending_commit_bumps)
		frappe.db.after_rollback.add(_clear_pending_rollback_bumps)


def clear_all_storefront_caches(*_args, **_kwargs) -> None:
	"""Called on frappe.clear_cache()."""
	_l1_api.clear()
	_l1_bytes.clear()
	_l1_ssr.clear()
	if dirty := getattr(frappe.local, "_commera_sf_dirty_domains", None):
		dirty.clear()
	if pending := getattr(frappe.local, "_commera_sf_pending_bumps", None):
		pending.clear()
	frappe.local._commera_sf_hooks_registered = False
	bump_epochs(*ALL_DOMAINS, immediate=True)


# Doc-event invalidators (accept any args, including 5-arg after_rename).
def bump_catalog(*_args, **_kwargs):
	bump_epochs("catalog")


def bump_prices(*_args, **_kwargs):
	bump_epochs("prices")


def bump_stock(*_args, **_kwargs):
	bump_epochs("stock")


def bump_discounts(*_args, **_kwargs):
	bump_epochs("discounts")


def bump_reviews(*_args, **_kwargs):
	bump_epochs("reviews")


def bump_shop(*_args, **_kwargs):
	bump_epochs("shop")


def bump_theme(*_args, **_kwargs):
	bump_epochs("theme")


def bump_party(*_args, **_kwargs):
	bump_epochs("party")


def bump_catalog_and_shop(*_args, **_kwargs):
	bump_epochs("catalog", "shop")


def bump_prices_and_shop(*_args, **_kwargs):
	bump_epochs("prices", "shop")


def bump_catalog_and_prices(*_args, **_kwargs):
	bump_epochs("catalog", "prices")


def _l1_get(store: OrderedDict, key: str):
	entry = store.get(key)
	if entry is None:
		return None
	expires_at, value = entry
	if time.monotonic() > expires_at:
		store.pop(key, None)
		return None
	store.move_to_end(key)
	return value


def _l1_set(store: OrderedDict, key: str, value: Any, ttl: int, max_entries: int):
	store[key] = (time.monotonic() + ttl, value)
	store.move_to_end(key)
	while len(store) > max_entries:
		store.popitem(last=False)


def _hash_key(prefix: str, parts: Any) -> str:
	raw = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
	if len(raw) <= 96:
		return f"commera:sfc:{prefix}:{raw}"
	digest = hashlib.blake2b(raw.encode("utf-8"), digest_size=16).hexdigest()
	return f"commera:sfc:{prefix}:{digest}"


def _locale_context() -> tuple[str, str, str]:
	from commera.localization import get_localization

	loc = get_localization()
	market_handle = loc.market.handle if loc.market else "primary"
	country = (loc.country or "").lower()
	return loc.language.code, market_handle, country


def _detect_http_api_version(endpoint: str | None) -> str | None:
	"""Return 'v1' or 'v2' when the current request is a direct HTTP call to `endpoint`, else None."""
	if not endpoint:
		return None
	req = getattr(frappe.local, "request", None)
	if not req or req.method != "GET":
		return None
	path = req.path or ""
	if path == f"/api/method/{endpoint}" or path == f"/api/v1/method/{endpoint}":
		return "v1"
	if path == f"/api/v2/method/{endpoint}":
		return "v2"
	return None


def _encode_api_bytes(payload: Any, api_version: str) -> bytes:
	wrapper = {"data": payload} if api_version == "v2" else {"message": payload}
	return json.dumps(wrapper, default=json_handler, separators=(",", ":")).encode("utf-8")


def _make_json_response(raw_bytes: bytes, *, cache_status: str, cache_control: str | None = None) -> Response:
	headers = {"X-Commera-Cache": cache_status}
	if cache_control:
		headers["Cache-Control"] = cache_control
	return Response(raw_bytes, status=200, mimetype="application/json", headers=headers)


def get_epoch_cached(
	namespace: str,
	key_parts: Any,
	domains: tuple[str, ...],
	compute_fn: Callable[[], Any],
	*,
	ttl: int = 300,
) -> Any:
	"""Epoch-keyed L2 Redis cache with TTL backstop for DB-derived flags and small lookup metadata."""
	if not is_cache_enabled() or _is_domain_dirty(domains):
		return compute_fn()
	key = _hash_key(f"flag:{namespace}", (_site(), epoch_stamp(domains), key_parts))
	cached = frappe.cache.get_value(key)
	if cached is not None:
		return cached
	value = compute_fn()
	frappe.cache.set_value(key, value, expires_in_sec=ttl)
	return value


def get_or_compute(
	namespace: str,
	key_parts: Any,
	domains: tuple[str, ...],
	compute_fn: Callable[[], Any],
	*,
	ttl: int = 60,
	include_locale: bool = True,
) -> Any:
	"""Epoch-versioned L1 + L2 cache returning isolated Python objects (safe for mutable callers)."""
	if not is_cache_enabled() or _is_domain_dirty(domains):
		return compute_fn()

	locale = _locale_context() if include_locale else ()
	key = _hash_key(
		namespace,
		(_site(), locale, epoch_stamp(domains), key_parts),
	)

	hit = _l1_get(_l1_api, key)
	if hit is not None:
		return copy.deepcopy(hit)

	l2 = frappe.cache.get_value(key)
	if l2 is not None:
		_l1_set(_l1_api, key, copy.deepcopy(l2), min(ttl, 30), L1_MAX_ENTRIES)
		return l2

	value = compute_fn()
	if value is not None:
		_l1_set(_l1_api, key, copy.deepcopy(value), min(ttl, 30), L1_MAX_ENTRIES)
		frappe.cache.set_value(key, value, expires_in_sec=ttl)
	return value


def cached_guest_api(
	namespace: str,
	key_parts: Any,
	domains: tuple[str, ...],
	compute_fn: Callable[[], Any],
	*,
	endpoint: str | None = None,
	ttl: int = 60,
	cache_control: str | None = None,
	guest_only: bool = True,
	include_locale: bool = True,
):
	"""Epoch-versioned L1+L2 cache for guest storefront GET APIs; returns pre-serialized Response over HTTP
	and the Python object for direct Python callers."""
	if not is_cache_enabled() or _is_domain_dirty(domains):
		return compute_fn()
	if guest_only and frappe.session.user != "Guest":
		return compute_fn()

	locale = _locale_context() if include_locale else ()
	stamp = epoch_stamp(domains)
	api_version = _detect_http_api_version(endpoint)

	if api_version is not None:
		bkey = _hash_key(f"b:{api_version}:{namespace}", (_site(), locale, stamp, key_parts))
		raw = _l1_get(_l1_bytes, bkey)
		if raw is not None:
			return _make_json_response(raw, cache_status="HIT-L1", cache_control=cache_control)

		raw_l2 = frappe.cache.get_value(bkey)
		if isinstance(raw_l2, bytes | bytearray):
			raw_bytes = bytes(raw_l2)
			_l1_set(_l1_bytes, bkey, raw_bytes, min(ttl, 30), L1_MAX_ENTRIES)
			return _make_json_response(raw_bytes, cache_status="HIT-L2", cache_control=cache_control)

		value = compute_fn()
		raw_bytes = _encode_api_bytes(value, api_version)
		_l1_set(_l1_bytes, bkey, raw_bytes, min(ttl, 30), L1_MAX_ENTRIES)
		frappe.cache.set_value(bkey, raw_bytes, expires_in_sec=ttl)
		return _make_json_response(raw_bytes, cache_status="MISS", cache_control=cache_control)

	return get_or_compute(
		namespace,
		key_parts,
		domains,
		compute_fn,
		ttl=ttl,
		include_locale=include_locale,
	)


def cached_cart_response(
	cart_name: str,
	revision: int,
	modified: str,
	compute_fn: Callable[[], dict],
	*,
	endpoint: str = "commera.api.storefront.cart.get_cart",
	ttl: int = 45,
):
	"""Revision-stamped cache for read-only cart.get_cart; invalidates on cart revision/modified or epoch bump."""
	domains = ("catalog", "prices", "discounts", "shop")
	if not is_cache_enabled() or _is_domain_dirty(domains):
		return compute_fn()

	locale = _locale_context()
	stamp = epoch_stamp(domains)
	key_parts = (cart_name, int(revision or 0), str(modified or ""))
	api_version = _detect_http_api_version(endpoint)

	if api_version is not None:
		bkey = _hash_key(f"cart:{api_version}", (_site(), locale, stamp, key_parts))
		raw = _l1_get(_l1_bytes, bkey)
		if raw is not None:
			return _make_json_response(raw, cache_status="HIT-L1", cache_control="private, no-store")
		raw_l2 = frappe.cache.get_value(bkey)
		if isinstance(raw_l2, bytes | bytearray):
			raw_bytes = bytes(raw_l2)
			_l1_set(_l1_bytes, bkey, raw_bytes, min(ttl, 20), L1_MAX_ENTRIES)
			return _make_json_response(raw_bytes, cache_status="HIT-L2", cache_control="private, no-store")
		value = compute_fn()
		raw_bytes = _encode_api_bytes(value, api_version)
		_l1_set(_l1_bytes, bkey, raw_bytes, min(ttl, 20), L1_MAX_ENTRIES)
		frappe.cache.set_value(bkey, raw_bytes, expires_in_sec=ttl)
		return _make_json_response(raw_bytes, cache_status="MISS", cache_control="private, no-store")

	return get_or_compute("cart", key_parts, domains, compute_fn, ttl=ttl, include_locale=True)


def cached_checkout_response(
	quotation_name: str,
	modified: str,
	compute_fn: Callable[[], dict],
	*,
	endpoint: str = "commera.api.storefront.checkout.get",
	ttl: int = 45,
):
	"""Modified-stamped cache for read-only checkout.get; invalidates on Quotation modified or epoch bump."""
	domains = ("catalog", "prices", "discounts", "shop")
	if not is_cache_enabled() or _is_domain_dirty(domains):
		return compute_fn()

	locale = _locale_context()
	stamp = epoch_stamp(domains)
	key_parts = (quotation_name, str(modified or ""))
	api_version = _detect_http_api_version(endpoint)

	if api_version is not None:
		bkey = _hash_key(f"chk:{api_version}", (_site(), locale, stamp, key_parts))
		raw = _l1_get(_l1_bytes, bkey)
		if raw is not None:
			return _make_json_response(raw, cache_status="HIT-L1", cache_control="private, no-store")
		raw_l2 = frappe.cache.get_value(bkey)
		if isinstance(raw_l2, bytes | bytearray):
			raw_bytes = bytes(raw_l2)
			_l1_set(_l1_bytes, bkey, raw_bytes, min(ttl, 20), L1_MAX_ENTRIES)
			return _make_json_response(raw_bytes, cache_status="HIT-L2", cache_control="private, no-store")
		value = compute_fn()
		raw_bytes = _encode_api_bytes(value, api_version)
		_l1_set(_l1_bytes, bkey, raw_bytes, min(ttl, 20), L1_MAX_ENTRIES)
		frappe.cache.set_value(bkey, raw_bytes, expires_in_sec=ttl)
		return _make_json_response(raw_bytes, cache_status="MISS", cache_control="private, no-store")

	return get_or_compute("checkout", key_parts, domains, compute_fn, ttl=ttl, include_locale=True)


# Guest SSR Page Cache (opt-in per page controller via `cacheable_ssr = True`)


def is_cacheable_ssr_request(route_path: str) -> bool:
	"""True only for anonymous, public, read-only GET requests to published storefront pages."""
	if not is_cache_enabled() or _is_domain_dirty(ALL_DOMAINS):
		return False
	if not frappe.flags.get("enable_storefront_cache_in_test") and (
		frappe.conf.get("developer_mode") or frappe._dev_server
	):
		return False
	req = getattr(frappe.local, "request", None)
	if not req or req.method != "GET":
		return False
	if getattr(frappe.local, "session", None) is None or frappe.session.user != "Guest":
		return False
	if req.headers.get("Authorization"):
		return False
	if getattr(frappe.session, "data", None) and frappe.session.data.get("csrf_token"):
		return False
	clean = (route_path or "").strip("/")
	first_seg = clean.split("/", 1)[0]
	if first_seg in NON_CACHEABLE_SSR_PREFIXES:
		return False
	if req.args:
		for param in req.args:
			if param in PREVIEW_QUERY_PARAMS:
				return False
	from commera.storefront_access import is_storefront_published

	if not is_storefront_published():
		return False
	return True


def _ssr_cache_key(route_path: str, localized=None) -> str:
	req = frappe.local.request
	if localized is not None:
		loc = localized.localization
		lang = loc.language.code
		market_handle = loc.market.handle if loc.market else "primary"
		country = (loc.country or "").lower()
	else:
		lang, market_handle, country = _locale_context()
	query_items = (
		sorted((k, v) for k, v in req.args.lists() if k in ALLOWED_SSR_QUERY_PARAMS) if req.args else []
	)
	return _hash_key(
		"ssr",
		(
			_site(),
			(route_path or "").strip("/"),
			query_items,
			lang,
			market_handle,
			country,
			epoch_stamp(ALL_DOMAINS),
		),
	)


def get_cached_ssr_response(route_path: str, localized=None) -> Response | None:
	if not is_cacheable_ssr_request(route_path):
		return None
	key = _ssr_cache_key(route_path, localized=localized)
	html_bytes = _l1_get(_l1_ssr, key)
	status = "HIT-L1"
	if html_bytes is None:
		raw = frappe.cache.get_value(key)
		if isinstance(raw, bytes | bytearray):
			html_bytes = bytes(raw)
			_l1_set(_l1_ssr, key, html_bytes, 30, L1_SSR_MAX_ENTRIES)
			status = "HIT-L2"
	if html_bytes is None:
		return None
	return Response(
		html_bytes,
		status=200,
		mimetype="text/html",
		headers={
			"Content-Type": "text/html; charset=utf-8",
			"X-Commera-Cache": status,
		},
	)


def store_cached_ssr_response(route_path: str, html: str, *, ttl: int = 60) -> None:
	if not is_cacheable_ssr_request(route_path):
		return
	if not html:
		return
	html_bytes = html.encode("utf-8") if isinstance(html, str) else bytes(html)
	if len(html_bytes) > MAX_SSR_CACHE_BYTES:
		return
	key = _ssr_cache_key(route_path)
	_l1_set(_l1_ssr, key, html_bytes, min(ttl, 30), L1_SSR_MAX_ENTRIES)
	frappe.cache.set_value(key, html_bytes, expires_in_sec=ttl)
