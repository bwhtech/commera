# Commera Cloud Image CDN — implementation plan

How product photos get resized, converted to modern formats and served from Cloudflare's edge at
`cdn.commera.cloud`, as a paid Commera Cloud add-on. Merchants never create a Cloudflare account or
paste a Cloudflare credential: BWH runs the Cloudflare side, the merchant's site only receives a
`site_id` and a signing secret when it connects.

Written against the Cloudflare developer docs as of 2026-09-29 (sources at the end). The Worker
code below is a design sketch, not tested code.

## Settled decisions

- **Originals stay on the merchant's site.** Nothing is uploaded or synced to Cloudflare. The CDN
  pulls `/files/...` from the merchant's origin the first time a size is requested.
- **Transform with the Images binding (`env.IMAGES`), not `fetch(url, { cf: { image } })`.** The
  Worker fetches the original itself, so it can check the tenant and the response before
  anything is transformed. It also needs no zone-level setup: `cf.image` on a zone requires
  enabling transformations and either listing every merchant domain under **Sources** or opening
  the zone to **any origin**. Opening it would let anyone use `cdn.commera.cloud/cdn-cgi/image/`
  on our bill.
- **Every rendered size is written to R2 and served from there afterwards.** Cloudflare bills a
  unique transformation again in every calendar month it is requested. A derivative read back
  from R2 is never transformed again, so each size of each photo is paid for once in its life.
- **Workers Cache in front of the renderer, and an uncached gateway in front of that.** The
  gateway runs on every request: it checks the signature and whether the tenant is active, and
  records usage. The renderer sits behind Workers Cache (tiered, with request collapsing), so a
  cache hit never runs it. See [Why a gateway](#why-a-gateway-and-not-one-cached-entrypoint).
- **URLs are signed and use a fixed width ladder.** Nobody can request arbitrary sizes and run up
  transformation charges.
- **Cache-busting by content hash, never by purge.** The URL carries the first 8 characters of the
  File's `content_hash`, so a replaced photo gets a new URL.
- **Failure means the original, not a broken image.** If a tenant is inactive or a render fails,
  the gateway redirects to the original on the merchant's site.

## Corrections to the earlier estimates

The docs changed three of the assumptions in the first cost sketch:

| Earlier assumption | What the docs say | Effect |
|---|---|---|
| Two formats cost two transformations | `format=auto` counts as one billable transformation on the URL/`cf.image` path. With the binding we pick formats explicitly, so assume each format counts separately until the first invoice says otherwise. | Keep the R2 write-once design. It makes this a one-off cost either way. |
| AVIF at every width | The AVIF output limit is **1,200 px**. Large images fall back to WebP or JPEG, and AVIF encoding is "an order of magnitude slower". | Only emit AVIF for widths ≤ 1,200. |
| Cache hits are free | With Workers Cache, **a hit is billed as a request** ($0.30/M), but uses no CPU. A `ctx.exports` loopback call is billed as a second request. | Gateway plus renderer is **2 billable requests per image**. That is $0.60 per million images. |

## Where it is hosted

| Thing | Where | Notes |
|---|---|---|
| Cloudflare account | Owned by BWH | 2FA on; add teammates as members, don't share logins |
| Zone `commera.cloud` | Cloudflare DNS | `central.commera.cloud` is a normal DNS record pointing at the Central Frappe host |
| Worker `commera-cdn` | Workers, custom domain `cdn.commera.cloud` | A custom domain creates the DNS record and certificate itself. Set `workers_dev: false` so there is no second public hostname |
| R2 bucket `commera-cdn-derivatives` | R2 | Rendered derivatives, keyed per tenant |
| KV namespace `commera-cdn-tenants` | Workers KV | Tenant registry, written only by the Worker's admin API |
| Analytics Engine dataset `commera_cdn_usage` | Workers Analytics Engine | Created automatically on first write |
| Source code | New repo `bwhtech/commera-edge` | Wrangler project, deployed from GitHub Actions |

**Subscriptions to turn on:**

- **Workers Paid** ($5/month). Required for Workers Cache limits, CPU headroom and R2/KV quotas.
- **Images Paid.** On Images Free, the 5,001st unique transformation of the month fails with error
  `9422`.
  - If the account still has the legacy "Image Resizing" subscription, the binding returns `9432`
    and the account must be moved to the Images subscription first.

## Request flow

```
Browser
  │ GET https://cdn.commera.cloud/acme/Xy3k…/w800_v3f9a1c2b/files/red-shirt.jpg
  ▼
Gateway (default entrypoint, cache disabled; runs every request)
  1. parse path, width must be on the ladder
  2. tenant = KV "tenant:acme" (in-isolate memo 60 s)        → unknown: 404
  3. HMAC-SHA256(secret, "acme/w800_v3f9a1c2b/files/red-shirt.jpg")[:16] == sig?  → no: 403
  4. tenant.active?                                           → no: 302 to original
  5. format from Accept: avif (≤1200px) → webp → jpeg
  6. write one Analytics Engine data point
  7. ctx.exports.Renderer({props:{site, origin}}).fetch("/r1/avif/w800_v3f9a1c2b/files/red-shirt.jpg")
  ▼
Workers Cache (lower tier → upper tier, request collapsing). HIT: returned without running Renderer
  ▼ MISS
Renderer (named entrypoint, cache enabled)
  8. R2 get "acme/r1/avif/w800_v3f9a1c2b/files/red-shirt.jpg"   → found: stream it
  9. fetch https://shop.acme.com/files/red-shirt.jpg (15 s timeout, must be image/*, ≤ 20 MB)
 10. env.IMAGES.input(body).transform({width, fit:"scale-down"}).output({format, quality})
 11. R2 put (waitUntil) and return with Cache-Control: public, max-age=31536000, immutable
```

The merchant's server is contacted only when a derivative misses both cache tiers **and** R2. That
is once per photo, format and width, ever.

### Why a gateway and not one cached entrypoint

With a single cached entrypoint, a cache hit never runs our code. Three things would then be
impossible:

- **Per-tenant usage.** Hits would never reach Analytics Engine. Workers Cache analytics is listed
  as "coming soon".
- **Instant suspension.** A cancelled tenant's images would keep serving from cache until they are
  purged.
- **Per-request signature checks.** A leaked URL would keep working.

The gateway costs one extra billed request per image and well under 1 ms of CPU. When Cloudflare
ships cache analytics we can revisit collapsing it into one entrypoint.

## URL format

```
https://cdn.commera.cloud/{site}/{sig}/w{width}_v{version}{path}

site     [a-z0-9-]{3,40}      Cloud Tenant id, e.g. "acme"
sig      22 chars base64url   first 16 bytes of HMAC-SHA256(secret, "{site}/w{width}_v{version}{path}")
width    one of 160 320 480 640 800 1200 1600
version  8 hex chars          first 8 of File.content_hash
path     /files/...           exactly as it appears in the URL (percent-encoded), public files only
```

- No query string is allowed. The Workers Cache key includes the query string and its order, so
  keeping everything in the path gives one cache entry per URL.
- `/private/files/...` never matches the pattern, so private files cannot be served.

## Worker code (`commera-edge`)

### `wrangler.jsonc`

```jsonc
{
  "name": "commera-cdn",
  "main": "src/index.ts",
  "compatibility_date": "2026-09-29",
  "compatibility_flags": ["enable_ctx_exports"],
  "workers_dev": false,
  "routes": [{ "pattern": "cdn.commera.cloud", "custom_domain": true }],

  // Share the cache across deploys. Output only changes when RENDER_VERSION is bumped,
  // and that is part of the inner path.
  "cache": { "enabled": true, "cross_version_cache": true },
  "exports": {
    "default": { "type": "worker", "cache": { "enabled": false } },
    "Renderer": { "type": "worker", "cache": { "enabled": true } }
  },

  "images": { "binding": "IMAGES" },
  "kv_namespaces": [{ "binding": "TENANTS", "id": "<kv namespace id>" }],
  "r2_buckets": [{ "binding": "DERIVATIVES", "bucket_name": "commera-cdn-derivatives" }],
  "analytics_engine_datasets": [{ "binding": "USAGE", "dataset": "commera_cdn_usage" }],
  "observability": { "enabled": true }
}
```

Secret: `npx wrangler secret put ADMIN_TOKEN`. This is the bearer token Central uses for the admin
API.

### `src/index.ts`

```ts
import { WorkerEntrypoint } from "cloudflare:workers";

interface Env {
  TENANTS: KVNamespace;
  DERIVATIVES: R2Bucket;
  IMAGES: ImagesBinding;
  USAGE: AnalyticsEngineDataset;
  ADMIN_TOKEN: string;
}
type Tenant = { origin: string; secret: string; active: boolean };
type Props = { site: string; origin: string };
type Format = "avif" | "webp" | "jpeg";

const WIDTHS = new Set([160, 320, 480, 640, 800, 1200, 1600]);
const AVIF_MAX_WIDTH = 1200; // Cloudflare's AVIF output limit
const RENDER_VERSION = "r1"; // bump to re-render every derivative (new quality, new encoder…)
const IMMUTABLE = "public, max-age=31536000, immutable";
const PATH = /^\/([a-z0-9-]{3,40})\/([A-Za-z0-9_-]{22})\/w(\d{3,4})_v([0-9a-f]{8})(\/files\/[^?#]+)$/;
const SITE = /^[a-z0-9-]{3,40}$/;
const enc = new TextEncoder();

// ---------- gateway: runs on every request ----------

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/_admin/")) return admin(request, env, ctx);
    if (request.method !== "GET" && request.method !== "HEAD") return text("Method not allowed", 405);

    const m = PATH.exec(url.pathname);
    if (!m || url.search) return text("Not found", 404);
    const [, site, sig, w, version, path] = m;
    const width = Number(w);
    if (!WIDTHS.has(width)) return text("Unsupported width", 400);

    const tenant = await getTenant(env, site);
    if (!tenant) return text("Not found", 404);
    if (!(await validSignature(tenant.secret, `${site}/w${w}_v${version}${path}`, sig))) {
      return text("Forbidden", 403);
    }
    if (!tenant.active) return toOriginal(tenant, path);

    const format = pickFormat(request.headers.get("Accept") ?? "", width);
    const renderer = ctx.exports.Renderer({ props: { site, origin: tenant.origin } });
    const res = await renderer.fetch(
      new Request(`https://renderer.internal/${RENDER_VERSION}/${format}/w${width}_v${version}${path}`),
    );
    env.USAGE.writeDataPoint({
      indexes: [site],
      blobs: ["request", format],
      doubles: [Number(res.headers.get("Content-Length") ?? 0)],
    });

    if (res.status === 404) return res;
    if (!res.ok) return toOriginal(tenant, path); // never show a broken image

    const out = new Response(res.body, res);
    out.headers.set("Vary", "Accept"); // same public URL, format depends on the browser
    out.headers.delete("Cache-Tag");
    return out;
  },
} satisfies ExportedHandler<Env>;

// ---------- renderer: behind Workers Cache ----------

export class Renderer extends WorkerEntrypoint<Env, Props> {
  async fetch(request: Request): Promise<Response> {
    const { site, origin } = this.ctx.props;
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/_purge") {
      await this.ctx.cache.purge({ tags: [`site-${site}`] });
      return text("purged", 200);
    }

    // /r1/avif/w800_v3f9a1c2b/files/red-shirt.jpg
    const [, , format, opts, ...rest] = url.pathname.split("/") as [string, string, Format, string, ...string[]];
    const path = "/" + rest.join("/");
    const width = Number(opts.slice(1, opts.indexOf("_")));
    const key = `${site}${url.pathname}`;
    const headers = { "Cache-Control": IMMUTABLE, "Cache-Tag": `site-${site}`, "Content-Type": `image/${format}` };

    const stored = await this.env.DERIVATIVES.get(key);
    if (stored) {
      this.env.USAGE.writeDataPoint({ indexes: [site], blobs: ["r2_hit", format], doubles: [stored.size] });
      return new Response(stored.body, { headers });
    }

    const source = await fetch(origin + path, {
      headers: { "User-Agent": "CommeraCDN/1.0 (+https://commera.cloud/cdn)" },
      signal: AbortSignal.timeout(15_000),
    }).catch(() => null);
    if (!source || !source.ok) {
      return source?.status === 404
        ? text("Not found", 404, "public, max-age=60")
        : text("Origin unavailable", 502, "no-store");
    }
    const type = source.headers.get("Content-Type") ?? "";
    if (!type.startsWith("image/") || type === "image/svg+xml") return text("Not an image", 502, "no-store");

    try {
      const output = await this.env.IMAGES.input(source.body!)
        .transform({ width, fit: "scale-down" })
        .output({ format: `image/${format}`, quality: 80 });
      const bytes = await output.response().arrayBuffer();
      this.ctx.waitUntil(this.env.DERIVATIVES.put(key, bytes, { httpMetadata: { contentType: `image/${format}` } }));
      this.env.USAGE.writeDataPoint({ indexes: [site], blobs: ["render", format], doubles: [bytes.byteLength] });
      return new Response(bytes, { headers });
    } catch {
      return text("Render failed", 502, "no-store"); // e.g. over 20 MB, corrupt file
    }
  }
}

// ---------- admin API: called only by Central ----------

async function admin(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const auth = enc.encode(request.headers.get("Authorization") ?? "");
  const expected = enc.encode(`Bearer ${env.ADMIN_TOKEN}`);
  if (auth.byteLength !== expected.byteLength || !crypto.subtle.timingSafeEqual(auth, expected)) {
    return text("Unauthorized", 401);
  }

  const m = /^\/_admin\/tenants\/([^/]+)(\/verify)?$/.exec(new URL(request.url).pathname);
  if (!m || !SITE.test(m[1])) return text("Not found", 404);
  const site = m[1];

  if (m[2] && request.method === "POST") {
    // Central calls this at connect time: can Cloudflare actually reach the merchant's files?
    const { origin, path } = await request.json<{ origin: string; path: string }>();
    const res = await fetch(origin + path, { signal: AbortSignal.timeout(15_000) }).catch(() => null);
    return Response.json({ status: res?.status ?? 0, type: res?.headers.get("Content-Type") ?? null });
  }

  if (request.method === "PUT") {
    const t = await request.json<Tenant>();
    const origin = new URL(t.origin);
    if (origin.protocol !== "https:" || origin.hostname.endsWith("commera.cloud") || origin.pathname !== "/") {
      return text("Invalid origin", 400);
    }
    await env.TENANTS.put(`tenant:${site}`, JSON.stringify({ origin: origin.origin, secret: t.secret, active: t.active }));
    return new Response(null, { status: 204 });
  }

  if (request.method === "DELETE") {
    const t = await getTenant(env, site, true);
    await env.TENANTS.delete(`tenant:${site}`);
    if (t) {
      await ctx.exports.Renderer({ props: { site, origin: t.origin } })
        .fetch(new Request("https://renderer.internal/_purge", { method: "POST" }));
    }
    ctx.waitUntil(deletePrefix(env.DERIVATIVES, `${site}/`));
    return new Response(null, { status: 202 });
  }

  return text("Method not allowed", 405);
}

// ---------- helpers ----------

const memo = new Map<string, { tenant: Tenant | null; at: number }>();

async function getTenant(env: Env, site: string, fresh = false): Promise<Tenant | null> {
  const hit = memo.get(site);
  if (!fresh && hit && Date.now() - hit.at < 60_000) return hit.tenant;
  const tenant = await env.TENANTS.get<Tenant>(`tenant:${site}`, { type: "json", cacheTtl: 60 });
  memo.set(site, { tenant, at: Date.now() });
  return tenant;
}

async function validSignature(secret: string, message: string, sig: string): Promise<boolean> {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(message))).slice(0, 16);
  const given = Uint8Array.from(atob(sig.replace(/-/g, "+").replace(/_/g, "/") + "=="), (c) => c.charCodeAt(0));
  return given.byteLength === 16 && crypto.subtle.timingSafeEqual(mac, given);
}

function pickFormat(accept: string, width: number): Format {
  if (accept.includes("image/avif") && width <= AVIF_MAX_WIDTH) return "avif";
  if (accept.includes("image/webp")) return "webp";
  return "jpeg";
}

function toOriginal(tenant: Tenant, path: string): Response {
  return new Response(null, { status: 302, headers: { Location: tenant.origin + path, "Cache-Control": "no-store" } });
}

function text(body: string, status: number, cacheControl = "no-store"): Response {
  return new Response(body, { status, headers: { "Cache-Control": cacheControl } });
}

async function deletePrefix(bucket: R2Bucket, prefix: string): Promise<void> {
  let cursor: string | undefined;
  do {
    const page = await bucket.list({ prefix, cursor, limit: 1000 });
    if (page.objects.length) await bucket.delete(page.objects.map((o) => o.key));
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);
}
```

Notes on the sketch:

- **Suspension delay.** Up to about 2 minutes: 60 s in-isolate memo plus the 60 s KV `cacheTtl`.
  That is fine for billing. A takedown should also call `DELETE`, which purges immediately.
- **Big tenants.** `deletePrefix` in `waitUntil` is enough for small and medium tenants. For large
  ones, move it to a Cron-triggered sweep over a "pending deletion" list.
- **Tests.** Use `@cloudflare/vitest-pool-workers`.
  - The Images binding runs as a low-fidelity mock locally: only `width`, `height`, `rotate` and
    `format` are supported.
  - Use `wrangler dev --remote` to exercise real transforms.

## Credentials

| Credential | Created where | Scope | Stored where | Used by |
|---|---|---|---|---|
| CI deploy token | Cloudflare → API Tokens, "Edit Cloudflare Workers" template | Account: Workers Scripts, KV, R2 edit. Zone `commera.cloud`: Workers Routes | GitHub Actions secrets `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` in `commera-edge` | `wrangler deploy` from CI only |
| Usage read token | Cloudflare → API Tokens, custom | Account → Account Analytics → Read. Nothing else | Central: Commera Cloud Settings (Password field) | Central's hourly usage pull |
| `ADMIN_TOKEN` | `openssl rand -base64 32` | The Worker's `/_admin/*` API only | Worker secret (`wrangler secret put`) and Central settings (Password field) | Central → Worker tenant push |
| Tenant signing secret | Central, 32 random bytes per tenant | Signs that tenant's image URLs | Central Cloud Tenant (Password), Worker KV, merchant site's Commera Cloud Settings (Password) | Merchant site signs; Worker verifies |

**What each side holds:**

- **Merchant sites** hold only their own `site_id` and signing secret, never a Cloudflare token.
- **Central** never holds a token that can deploy or edit Workers.
- **Rotation:**
  - Signing secrets: Central writes a new one to KV and to the site. For a short overlap, KV can
    hold `secret` and `previous_secret`, and the Worker accepts either.
  - `ADMIN_TOKEN`: set a new Worker secret, then update Central.

## Commera side (this repo)

`commera/cloud/` module:

- **Commera Cloud Settings** (Single). Fields:
  - `enabled`, `site_id`, `signing_secret` (Password), `cdn_base_url` (default
    `https://cdn.commera.cloud`), `image_cdn_active` (set by the entitlements refresh).
  - Filled by the connect handshake, never by hand.
- **`commera/cloud/image_cdn.py`**:

  ```python
  WIDTHS = (160, 320, 480, 640, 800, 1200, 1600)

  def cdn_url(file_url: str, width: int) -> str:
      settings = frappe.get_cached_doc("Commera Cloud Settings")
      if not (settings.enabled and settings.image_cdn_active) or not file_url.startswith("/files/"):
          return file_url  # later: local Pillow resizer

      width = next((w for w in WIDTHS if w >= width), WIDTHS[-1])
      path = quote(file_url, safe="/")  # sign exactly what appears in the URL
      opts = f"w{width}_v{content_version(file_url)}"
      message = f"{settings.site_id}/{opts}{path}".encode()
      mac = hmac.new(settings.get_password("signing_secret").encode(), message, hashlib.sha256).digest()[:16]
      sig = base64.urlsafe_b64encode(mac).rstrip(b"=").decode()
      return f"{settings.cdn_base_url}/{settings.site_id}/{sig}/{opts}{path}"
  ```

  - `content_version(file_url)` is the first 8 characters of `File.content_hash`. Cache it in a
    Redis hash keyed by `file_url`, cleared on `File.on_update` / `on_trash`.
  - Fall back to hashing `file_url` plus `modified` when `content_hash` is empty.
- **`srcset(file_url, widths, sizes)`** and a **`commera_image`** Jinja macro. They write `src`,
  `srcset`, `sizes`, `width`/`height`, `loading="lazy"` and `decoding="async"`, plus
  `fetchpriority="high"` for the main product photo.
- **The Python sources that feed Alpine templates** call `cdn_url` too:
  - `utils.py:134`, `product_detail.py:43`, `search/record_builder.py:264`, `checkout.py:104`.
  - This covers the cart, search, wishlist and gallery.

## Central side (`commera_central`)

- **Cloud Tenant** `on_update` enqueues `push_tenant`:
  - `PUT {cdn}/_admin/tenants/{site_id}` with `{origin, secret, active}`.
  - On cancellation, `DELETE`.
  - A nightly job re-pushes every tenant to repair drift.
- **Connect handshake.** Before activating the add-on, Central calls `POST /_admin/tenants/{site_id}/verify`
  with one of the merchant's real `/files/` paths. It refuses with a clear message if Cloudflare
  gets anything other than `200 image/*`. This typically catches:
  - a local or intranet site
  - the merchant's own Cloudflare bot protection blocking us, fixed by allowing the `CommeraCDN`
    user agent
- **Hourly usage pull.** Rows go into Cloud Usage, and Central is the record. Analytics Engine
  samples at high volume, so always weight by `_sample_interval`.

  ```sql
  SELECT index1 AS site, blob1 AS event,
         SUM(_sample_interval) AS count, SUM(_sample_interval * double1) AS bytes
  FROM commera_cdn_usage
  WHERE timestamp >= toDateTime('2026-09-01 00:00:00') AND timestamp < toDateTime('2026-10-01 00:00:00')
  GROUP BY site, event
  ```

  POST it to `https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql` with
  the usage read token.

## Cost model (verified prices)

| Item | Price | Per image served |
|---|---|---|
| Workers Paid | $5/month; 10M requests and 30M CPU-ms included | — |
| Worker requests | $0.30 per million | 2 requests (gateway + renderer, hit or miss) = **$0.60 per million images** |
| CPU | $0.02 per million CPU-ms | Gateway ≈ 1 ms; renderer only on a miss |
| Images transformations | 5,000/month included, then $0.50 per 1,000 unique | Once per photo × width × format, ever (R2) |
| R2 | $0.015/GB-month (10 GB free), $4.50/M writes, $0.36/M reads, no egress | Writes once per derivative; reads only on a cache miss |
| KV | 10M reads/month included, then $0.50/M | Few, because of the in-isolate memo |
| Analytics Engine | Not billed yet; announced at $0.25/M data points | 1 per image |

A medium store (2,000 products, 8,000 photos, about 12M images served a month):

- **Requests:** about $7.20/month.
- **Transforms for newly uploaded photos:** a few dollars a month.
- **Back catalogue:** a one-off of up to about $48, if every width and format of every photo is
  eventually requested.

The main unknown is images served per visit. Browser caching (`immutable`, one year) and lazy
loading will put real numbers well below the "25 images per page view" assumption. Measure it on
the pilot store before fixing plan prices.

## Rollout

1. **Set up Cloudflare.** Create the account resources: zone, Workers Paid, Images Paid, R2 bucket,
   KV namespace and tokens. Create `commera-edge` with CI deploy.
2. **Deploy the Worker.** Add one tenant with `curl` to `/_admin/tenants/demo`, pointing at the
   demo store. Check:
   - a first request returns `Content-Type: image/avif`
   - a repeat request has `Cf-Cache-Status: HIT`
   - the object exists in R2
   - a wrong signature returns 403
   - `active:false` returns a 302 to the original
3. **Commera side.** Build Commera Cloud Settings, `cdn_url`, the `commera_image` macro, and the
   template and data-source switch-over, behind `image_cdn_active`.
4. **Pilot.** Run it for a month on one real store, and read the usage rows before setting prices.
5. **Central.** Add Cloud Tenant push and the connect handshake with verify, then open it to
   customers.

## Open questions

- Confirm on the first invoice whether explicit `image/avif` and `image/webp` outputs from the
  binding count as one unique transformation or two.
- Workers Cache is new:
  - At launch, all cached responses use the Free-plan size limit (512 MB), which is irrelevant for
    images.
  - Purges use Free-tier rate limits. Keep purges to tenant deletion.
- Should the width ladder include 2,000+ for zoom views? AVIF stops at 1,200, so those would be
  WebP only.

## Sources

- Images: [pricing](https://developers.cloudflare.com/images/pricing/),
  [limits and formats](https://developers.cloudflare.com/images/get-started/limits/),
  [Images binding](https://developers.cloudflare.com/images/optimization/binding/),
  [transform via fetch](https://developers.cloudflare.com/images/optimization/transformations/transform-via-workers/),
  [source origins](https://developers.cloudflare.com/images/optimization/transformations/sources/),
  [features](https://developers.cloudflare.com/images/optimization/features/),
  [troubleshooting / error codes](https://developers.cloudflare.com/images/reference/troubleshooting/)
- Workers Cache: [overview](https://developers.cloudflare.com/workers/cache/),
  [cache keys](https://developers.cloudflare.com/workers/cache/cache-keys/),
  [gateway examples](https://developers.cloudflare.com/workers/cache/examples/),
  [purge](https://developers.cloudflare.com/workers/cache/purge/),
  [limitations](https://developers.cloudflare.com/workers/cache/limitations/)
- Workers: [pricing](https://developers.cloudflare.com/workers/platform/pricing/),
  [limits](https://developers.cloudflare.com/workers/platform/limits/),
  [context / `ctx.exports`](https://developers.cloudflare.com/workers/runtime-apis/context/),
  [custom domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/),
  [secrets](https://developers.cloudflare.com/workers/configuration/secrets/),
  [Web Crypto](https://developers.cloudflare.com/workers/runtime-apis/web-crypto/)
- Storage and analytics: [R2 pricing](https://developers.cloudflare.com/r2/pricing/),
  [R2 Workers API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/),
  [KV read API](https://developers.cloudflare.com/kv/api/read-key-value-pairs/),
  [KV pricing](https://developers.cloudflare.com/kv/platform/pricing/),
  [Analytics Engine](https://developers.cloudflare.com/analytics/analytics-engine/get-started/),
  [SQL API](https://developers.cloudflare.com/analytics/analytics-engine/sql-api/),
  [Analytics Engine pricing](https://developers.cloudflare.com/analytics/analytics-engine/pricing/)
