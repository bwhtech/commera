# Commera Apps — Platform implementation

Spec 2 of 3. What Commera builds so the [developer API](01-developer-api.md) works. File paths are
proposals unless they name existing code; line numbers are from `e606f77`.

Status: draft.

## Overview

```
 app hooks.py ──► commera/extensions/registry.py ──► www/commera.py boot ──► dashboard
 (dotted paths)   (collect, validate, cache,          (visible entries      ia/extensions.js
                   filter per user)                    per user)             ExtensionSlot.vue
                                                                              import(module URL)
 app commera/*.vue ──► @commera/extension-kit (vite) ──► app/public/commera/<module>.js ─┘
```

Server work (order hooks, made-to-order, parcels, integration lists, SDK) is independent of the
dashboard runtime and can ship first.

---

## 1. Server

### 1.1 Extension registry — `commera/extensions/`

| File | Holds |
| --- | --- |
| `commera/sdk/extensions.py` | `Target` enum, builders, `ICONS`, `ExtensionDefinitionError` (public API, spec 1 §1) |
| `commera/extensions/registry.py` | `get_registry()`, `get_visible_extensions(user)`, `resolve_record_conditions(doctype, name)` |
| `commera/extensions/validate.py` | Schema + build checks, "did you mean" suggestions |
| `commera/extensions/commands.py` | `bench commera …` click commands (registered via `commera/commands.py`) |
| `commera/sdk/testing.py` | `assert_extensions_valid(app)` |

`get_registry()`:

1. For each installed app, `frappe.get_hooks("commera_extensions", app_name=app)`; call each dotted
   path; tag entries with `app`; key = `f"{app}:{handle}"`.
2. Validate each entry (§1.2). An invalid entry is logged with `frappe.log_error` and dropped; it never
   breaks the dashboard.
3. For entries with a `module`, resolve `/assets/<app>/commera/<module>.js` and stat the file:
   missing → error recorded for the Developer tab; present → `url = …?v=<mtime>`.
4. Cache in `frappe.cache` under `commera:extensions`; cleared by the `clear_cache` hook and
   `after_migrate`. **Developer mode skips the cache.**

`get_visible_extensions(user)` filters by the merchant switch (§1.6), `requires` read permission and
user-level `condition`. Record-level conditions are omitted from boot and flagged `record_condition`.

`resolve_record_conditions(doctype, name)` — whitelisted, one call per record page, returns the
handles whose record-level condition passed. Each condition runs in `try/except`; a raising condition
counts as hidden and is logged.

### 1.2 Validation

- Known `target`; required arguments per target; unique `<app>:<handle>`.
- `condition` / `method` import and are callable; action methods are in `frappe.whitelisted`.
- `requires` / `settings` DocTypes exist; `settings` is a Single.
- `icon` in `ICONS`.
- Module file exists and carries a supported API version (read from a header comment the kit writes).

Runs in `get_registry()` (log + drop), `bench commera extensions validate` (report + non-zero exit),
`after_migrate` (log), and `assert_extensions_valid` (raise).

### 1.3 Boot

`commera/www/commera.py` adds `context.boot.extensions = get_visible_extensions(frappe.session.user)`
and `context.boot.translations = get_all_translations(frappe.local.lang)` (Frappe's merged
translations, `frappe/translate.py:135`; Commera already serves the same data as
`commera.api.utils.get_translations`). Size budget: translations for non-English only.

### 1.4 Order hooks

Today `place_order` (`commera/api/payments.py:288`) submits the Sales Order before the invoice and
Payment Entry exist, inside the Gateway Payment Request hook's transaction; COD orders are drafts
(`place_cod_order`, `payments.py:580`); a shopper cancelling a COD draft submits then cancels it
(`commera/api/orders.py:27`).

- New `commera/order_events.py`:
  - `fire(event, sales_order)` enqueues `run_hooks` with `enqueue_after_commit=True`,
    `job_id=f"commera:{event}:{sales_order}"`, `deduplicate=True`. The job runs as Administrator and
    restores the user; each handler is isolated (`try/except` + `log_error`).
  - A **Commera Order Event** log (`sales_order`, `event`, unique together) makes each event fire once
    even across retries.
- Call sites:
  - `commera_order_placed`: end of `place_order`; end of `place_cod_order`.
  - `commera_order_paid`: end of `place_order` when `gateway_amount > 0`; new `doc_events` on
    **Payment Entry** `on_submit` for Receive entries against a webshop order's invoice (COD
    collection).
  - `commera_before_order_cancel`: in `validate_can_cancel` (`commera/api/orders.py:147`) and in a
    Sales Order `before_cancel` doc event (Desk path). First non-`None` reason refuses with
    `frappe.throw`. The COD shopper-cancel path calls it before `submit()` so no `placed` hook ever
    sees a draft that is about to be cancelled.

### 1.5 Made-to-order items

- `Item` custom field `custom_made_to_order` (Check), copied to variants.
- `validate_stock_available` (`commera/api/cart.py:49`) skips made-to-order lines.
- Product page stock (`commera/product_detail.py`) reports made-to-order sizes as in stock.
- `create_product` (`commera/api/admin/catalog.py:1151`) accepts `made_to_order`; sets
  `is_stock_item = 0` instead of forcing `1` (`catalog.py:1225`).

### 1.6 Shipping parcels

`get_cart_parcels` (`commera/api/shipping.py:150`) adds `items: [{item_code, qty}]`; bwh_shipping's
`normalise_parcel` already carries it (`bwh_shipping/units.py:75`). The cart fingerprint already
includes item codes, so caching is unaffected.

### 1.7 Hook-driven integration lists

`SHIPPING_PROVIDERS` (`commera/api/admin/shipping.py:13`) and `PAYMENT_GATEWAYS`
(`commera/api/admin/payments.py:14`) become the built-in entries; the registries append
`frappe.get_hooks("commera_shipping_providers" | "commera_payment_gateways")` results. Slug lookup,
`get_link_options` and the unchanged `describe_integration` engine read the merged list. Fix the
empty-state copy in `IntegrationsPanel.vue` accordingly.

### 1.8 SDK

`commera/sdk/catalog.py` wraps `create_product` / `update_product` / `set_variant_published`
with a stable signature, `external_id` upsert (custom field on Item) and `owner` tracking for
unpublish. `commera/sdk/orders.py:record_shipment` inserts a **Shipping Request** (`ref_doctype =
"Sales Order"`, provider profile, origin/destination addresses, one parcel, `awb`, tracking events) so
`get_carrier_status` (`commera/utils.py:707`) drives the Shipped state.

### 1.9 Merchant switches

Single DocType **Commera Extension Settings** with a child table (`extension_key`, `enabled`).
Absent row = enabled. Written from **Settings → Installed apps**.

---

## 2. Dashboard

### 2.1 Shared runtime

- `vite.config.js`: additional entries `runtime/vue`, `runtime/frappe-ui`, `runtime/commera-admin`
  with `preserveEntrySignatures: 'exports-only'`, so the dashboard's own imports and extensions share
  one instance of each.
- A small Vite plugin writes `<script type="importmap">` into `commera/www/commera.html` before the
  entry script, mapping `vue`, `frappe-ui`, `@commera/admin` to those hashed files.
- **All of frappe-ui is shared (`export *`), not a curated list.** Measured on the real dashboard
  build: +15 kB gzip on first load over no sharing; a list of the 57 names the dashboard imports would
  save only 2 kB of that. Bundling frappe-ui into extensions instead breaks module-level state: a
  `toast` imported from `frappe-ui` never shows (`poc/extension-runtime/experiment-bundled-toast.mjs`).
- The build also emits `shared-exports.json` (each shared specifier's export names, read from the
  runtime chunks). The kit checks extension imports against it, which catches an app built against a
  newer frappe-ui than the site runs.

### 2.2 `@commera/admin` — `dashboard/src/extension-api/index.js`

Re-exports `useMethodRead`, `useMethodAction` (`data/api.js`), `AppPageHeader`, `PageBody`,
`EmptyState`, `StatusBadge`, `ListPagination`, `ResponsiveButton`, `money`, `shortDate`; adds
`useExtension`, `usePolling`, `ExtensionCard`, and `__` (lookup in `boot.translations`).

### 2.3 Rendering

| File | Does |
| --- | --- |
| `ia/extensions.js` | Reads `boot.extensions`; groups by target; `navSections()` merges `NAV_LINK` into `ia/nav.js` `sections` (new trailing **Apps** section; never reorders core items) |
| `components/ExtensionSlot.vue` | Props `target`, `resource`. Resolves record conditions (one call per page), lazy-imports modules with `defineAsyncComponent`, provides the `useExtension` context, wraps each in an `onErrorCaptured` boundary that shows a small failure card and reports to the Developer tab. Renders nothing for an extension that renders nothing |
| `components/ExtensionActions.js` | Turns action entries into Dropdown options; declarative actions POST `method` and toast `message`; module actions open a Dialog |
| `pages/ExtensionPage.vue` | Route `/apps/:app/:page/:path(.*)*`; hosts `APP_PAGE` modules |
| `components/settings/ExtensionSettingsPanel.vue` | Declarative `settings()` tab: `SettingsFieldRows` + `useSettingsAutosave` over the Single DocType; secrets via the `write_settings` blank-keeps-stored rule |
| `components/settings/InstalledApps.vue` | **Settings → Installed apps** (slug `installed-apps`; `apps` is taken by Analytics, `ia/settings.js:39`): per-extension switches, and a Discover list from the FC marketplace API via a cached server proxy |
| `components/settings/DeveloperPanel.vue` | Developer mode only: registry, module URLs, API version, validation and boundary errors |

Slot placements (edits to existing pages):

- `OrderDetail.vue`: `<ExtensionSlot target="admin.order-details.block">` in the `<aside>` (l.222) and
  in the `lg:hidden` stack (l.215); action entries appended to `moreActions` (l.51).
- `ProductDetail.vue`: block after the section stack; actions appended via `ia/productActions.js`.
- `CustomerDetail.vue`: block and actions, same pattern.
- `Orders.vue`, `Products.vue`, `Customers.vue`: index actions in the header `#actions`; selection
  actions in `BulkBar`.
- `AppSettingsDialog.vue`: one `SettingsNavItem` + `SettingsPanel` per `settings()` entry; `router.js`
  `beforeEnter` accepts `ext-<app>-<handle>` tabs.

### 2.4 Styling guard

The dashboard build emits `public/commera/classes.json` (every generated class). The kit loads it
from the sibling `apps/commera` build and fails the extension build on unknown classes. Curated Lucide
icons are safelisted in `tailwind.config.js` from `commera/sdk/extensions.py`'s `ICONS` (generated
JSON, one source).

---

## 3. Extension kit — `packages/extension-kit/`

- `vite.js`: discovers `commera/*/index.vue`, library mode, ES output, externals, fixed entry names,
  API-version header, class check (§2.4), no CSS emission (fails on `<style>`).
- `types/`: declarations for `@commera/admin`.
- `testing/`: Puppeteer helpers mirroring `dashboard/tests/e2e`.
- Consumed as `file:../commera/packages/extension-kit`; published to npm later.

---

## 4. Phases

| Phase | Ships | Depends on |
| --- | --- | --- |
| P0 spike | Import-map shared runtime; sibling-app component renders with toast + Dialog; bundle-size delta measured | — |
| P1 server | Order hooks (§1.4), made-to-order (§1.5), parcel items (§1.6), hook-driven integration lists (§1.7) | — |
| P2 registry + nav | `commera.sdk.extensions`, registry, boot, `NAV_LINK`, Installed apps switches, CLI `list` / `validate`, docs | — |
| P3 pages | Kit v0, `APP_PAGE`, `ExtensionSlot`, Developer tab, `new-extension`, `types` | P0, P2 |
| P4 records | Blocks, actions (declarative + module), selection actions, record conditions, `settings()` tab | P3 |
| P5 SDK | `commera.sdk.catalog`, `commera.sdk.orders` | P1 |
| P6 marketplace | Discover list from FC API | FC endpoint |

Each phase ships with tests: registry and validation unit tests, order-hook tests (placed/paid fire
once; COD cancel never fires placed), made-to-order checkout test, and an e2e spec driving a fixture
app's link, page and order block.

## Risks

- **frappe-ui version coupling.** A frappe-ui major bump in Commera is an extension API bump; apps
  rebuild. Mitigated by the stamped API version and a supported-previous-version window.
- **Shared-runtime bundle size.** Measured in P0 before committing.
- **bwh_shipping carrier contract** assumes the store books labels; rates-only carriers need either a
  mode in `ShippingProviderBase` or refusal stubs (decide with bwh_shipping owners).
