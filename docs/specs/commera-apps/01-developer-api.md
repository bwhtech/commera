# Commera Apps — Developer API

Spec 1 of 3. What an app developer writes to extend Commera: the registration API, the dashboard
extension API, the server SDK, the build kit and the CLI. [Spec 2](02-platform-implementation.md)
is how Commera implements it; [spec 3](03-example-printful.md) is a full app built on it.

Status: draft. Nothing here exists yet.

## Goals

- A Commera app is an **ordinary Frappe app**: `bench new-app`, `required_apps = ["bwhtech/commera"]`,
  `bench get-app` / `install-app`, the Frappe Cloud marketplace. No second packaging format.
- The first extension is a **sidebar link**; the same registry grows to full pages, record blocks,
  actions and settings without a new mechanism.
- Extensions **look native** because they *are* native: Vue components rendered inside the dashboard
  with its own Vue and frappe-ui, not iframes or shadow roots.
- Mistakes fail **early and loudly**: at import, in the editor, in `validate`, in the Developer tab —
  never as a blank dashboard.

## Non-goals (v1)

- Sandboxing. An installed Frappe app already runs arbitrary server code; the dashboard trusts it the
  same way. Isolation is for robustness (one broken extension shows one failure card), not security.
- Extension CSS. Extensions use frappe-ui and the dashboard's class vocabulary only (see *Styling*).
- A billing API. Paid apps are billed by the Frappe Cloud marketplace.
- Hot module reload for extensions (the watcher + focus reload covers v1).

---

## 1. Registering extensions

`hooks.py` holds only dotted paths; it imports nothing, because Frappe loads and caches every app's
hooks early.

```python
# my_app/hooks.py
required_apps = ["bwhtech/commera"]

commera_extensions = ["my_app.commera.extensions.get_extensions"]
```

Each path names a function that returns a list of entries built with `commera.sdk.extensions`:

```python
# my_app/commera/extensions.py
from commera.sdk.extensions import Target, action, app_page, block, nav_link, settings

from my_app.api import start_sync
from my_app.orders import is_my_order


def get_extensions():
    return [
        nav_link("Loyalty", icon="gift", page="loyalty"),
        app_page("loyalty", module="loyalty-page", requires="Loyalty Settings"),
        block(Target.ORDER_DETAILS, module="loyalty-order-block",
              requires="Loyalty Ledger", condition=is_my_order),
        action(Target.PRODUCT_INDEX, "Sync points", method=start_sync),
        settings("Loyalty Settings"),
    ]
```

Raw dicts in `hooks.py` are **not** supported: one style for every app, and the builders are where
validation lives.

### 1.1 Targets

`Target` is a `StrEnum`. Values are stable strings; renaming one is a breaking API change.

| Target | Value | Renders | Needs a module? |
| --- | --- | --- | --- |
| `NAV_LINK` | `admin.nav.link` | A row in the sidebar's **Apps** section (or Catalog / Storefront) | No |
| `APP_PAGE` | `admin.app.page` | A full page at `/commera/apps/<app>/<page>/*` | Yes |
| `ORDER_DETAILS` | `admin.order-details.block` | A card on the order page (side column ≥ `lg`, inline below) | Yes |
| `PRODUCT_DETAILS` | `admin.product-details.block` | A card on the product page | Yes |
| `CUSTOMER_DETAILS` | `admin.customer-details.block` | A card on the customer page | Yes |
| `ORDER_ACTION` / `PRODUCT_ACTION` / `CUSTOMER_ACTION` | `admin.<resource>-details.action` | An item in the record page's **More actions** menu | Optional |
| `ORDER_INDEX` / `PRODUCT_INDEX` / `CUSTOMER_INDEX` | `admin.<resource>-index.action` | An item in the list page header menu | Optional |
| `ORDER_SELECTION` / `PRODUCT_SELECTION` | `admin.<resource>-index.selection-action` | An item in the list's bulk bar | Optional |
| `SETTINGS` | `admin.settings.tab` | A tab in the Settings dialog | No |

### 1.2 Builders

All builders return plain dicts. Common keyword arguments:

| Argument | Type | Meaning |
| --- | --- | --- |
| `handle` | `str` | Unique within the app. Defaults to `module`, else a slug of `label`. Registry key is `<app>:<handle>` and must never change once shipped. |
| `requires` | `str` (DocType) | Shown only to users with **read** permission on this DocType. `nav_link` inherits it from its `page`. |
| `condition` | callable | User-level: `() -> bool`. Record-level targets: `(doctype: str, name: str) -> bool`. |
| `module` | `str` | Folder name under the app's `commera/` source directory (see §4). |

```python
nav_link(label: str, *, icon: str, page: str | None = None, url: str | None = None,
         section: Literal["apps", "catalog", "storefront"] = "apps", **common)
app_page(page: str, *, module: str, title: str | None = None, **common)
block(target: Target, *, module: str, **common)
action(target: Target, label: str, *, method: Callable | None = None, module: str | None = None,
       icon: str | None = None, confirm: str | None = None, **common)
settings(doctype: str, *, label: str | None = None, **common)
```

Rules the builders enforce (they raise `ExtensionDefinitionError` at call time):

- `nav_link` takes exactly one of `page` / `url`. `url` must be a path starting with `/` (not `//`)
  or `https://`.
- `icon` must be in the curated Lucide set (`commera.sdk.extensions.ICONS`).
- `action` takes exactly one of `method` (declarative: POST, then toast the returned `message`) or
  `module` (a dialog component).
- `method` / `condition` must be **functions**, not strings. The builder derives the dotted path
  from `__module__` / `__qualname__`; an action's `method` must be `@frappe.whitelist`ed.
- `settings(doctype)` must name a **Single** DocType.

### 1.3 Visibility

Evaluated on the server, never in the browser:

1. The app is installed on the site (automatic: `frappe.get_hooks` only returns installed apps).
2. The merchant has not switched the extension off in **Settings → Installed apps**.
3. `requires`: the user can read that DocType.
4. `condition`: user-level conditions run at boot; record-level conditions run once per record page,
   batched into one request for every extension on that page.

A **block** may also hide itself by rendering nothing; the slot collapses with no empty card.

---

## 2. Dashboard extension API (`@commera/admin`)

An extension module is a Vue SFC whose default export is the component. It imports from three
shared modules only — `vue`, `frappe-ui`, `@commera/admin` — which resolve to the dashboard's own
copies at runtime. Anything else it imports is bundled into the extension. Anything `frappe-ui` exports may
be imported; the kit's build fails on a name the site's frappe-ui version does not export, and on
`frappe-ui/…` subpaths.

```vue
<!-- my_app/commera/loyalty-order-block/index.vue -->
<script setup>
import { ExtensionCard, money, useExtension, useMethodRead } from '@commera/admin'

const { resource, __ } = useExtension()   // { doctype: 'Sales Order', name: 'SAL-ORD-…' }
const ledger = useMethodRead('my_app.api.get_order_points', {
  params: { sales_order: resource.name },
})
</script>

<template>
  <ExtensionCard v-if="ledger.data" :title="__('Loyalty')">
    {{ __('Earned') }}: {{ ledger.data.points }}
  </ExtensionCard>
</template>
```

### 2.1 `useExtension()`

| Member | Available on | Meaning |
| --- | --- | --- |
| `resource` | record targets | `{ doctype, name }` of the record the page shows |
| `selection` | selection actions | `string[]` of selected record names |
| `path`, `query` | `APP_PAGE` | The sub-path under the page's base, and the query object |
| `navigate(to)` | all | Router push. Relative paths stay inside the app page's base; absolute paths (`/orders/…`) go to dashboard routes |
| `setTitle(title)` | `APP_PAGE` | Browser title and breadcrumb |
| `close(result?)` | module actions | Closes the action dialog |
| `toast` | all | frappe-ui's toast |
| `__(text, replacements?)` | all | Translation, from Frappe's merged translations for the session language |
| `boot` | all | `{ lang, isRtl, currency, currencySymbol, dateFormat, timeFormat }` |
| `extension` | all | `{ app, handle, target }` |

`bench commera extensions types` generates per-target TypeScript types, so an editor knows that
`resource.doctype` is `'Sales Order'` inside an order block.

### 2.2 Data

`useMethodRead(path, options)` / `useMethodAction(path, options)` — the dashboard's own helpers,
re-exported. `path` is a full dotted path to a whitelisted method (`my_app.api.get_order_points`).
They call `/api/v2/method/`, toast failures (never toast again in the component), and support
`quiet: true` for expected refusals. `usePolling(request, { every: ms, while: () => bool })` reloads
a read on an interval while a condition holds.

**Do not** use `fetch`, `frappe.call`, or frappe-ui's `useCall` / `createResource` directly; v1
paths silently resolve to `null` in this dashboard.

### 2.3 Components

Re-exported so extensions match native screens: `AppPageHeader`, `PageBody`, `ExtensionCard`,
`EmptyState`, `StatusBadge`, `ListPagination`, `ResponsiveButton`, plus `money` and `shortDate`
formatters. Everything else comes from `frappe-ui` (Button, Dialog, Select, ListView, Badge, …).

### 2.4 Styling

- No extension CSS in v1: no `<style>` blocks, no stylesheet imports.
- Utility classes must be ones the dashboard already ships. The kit's build fails on any other
  class, with a suggestion where one exists. Tokens only (`text-ink-gray-7`, `bg-surface-gray-2`);
  no hex colours, no arbitrary values, no string-built class names.
- Icons: `<span class="lucide-<name> size-4" aria-hidden="true" />` from the curated set.

---

## 3. Server SDK (`commera.sdk`)

Stable Python APIs for flows Commera owns. Versioned with the extension API; anything outside
`commera.sdk` (including `commera.api.admin.*`) is internal and may change without notice.

### 3.1 Hooks Commera fires

```python
# my_app/hooks.py
commera_order_placed = ["my_app.orders.on_order_placed"]      # (sales_order: str)
commera_order_paid = ["my_app.orders.on_order_paid"]          # (sales_order: str)
commera_before_order_cancel = ["my_app.orders.can_cancel"]    # (sales_order: str) -> str | None
commera_shipping_providers = ["my_app.carrier.provider"]      # () -> dict (integration card)
commera_payment_gateways = ["my_app.gateway.gateway"]         # () -> dict (integration card)
```

| Hook | When | Contract |
| --- | --- | --- |
| `commera_order_placed` | Once per webshop order, **after commit**: gateway orders when placed, COD orders when the shopper places the draft | Runs in a background job as a system user. Never inside checkout's transaction |
| `commera_order_paid` | Once per order, after commit, when payment is recorded (gateway capture, or a COD Payment Entry) | Same as above |
| `commera_before_order_cancel` | Before a merchant or shopper cancel | Return a translated reason string to refuse; `None` to allow |
| `commera_shipping_providers` / `commera_payment_gateways` | Settings → Shipping / Payments render | Return the card: `{slug, label, blurb, settings_doctype, docs_url}` |

### 3.2 Catalog and orders

```python
from commera.sdk import catalog, orders

catalog.upsert_product(external_id=..., title=..., collection=..., options=[...], images=[...],
                       prices={...}, made_to_order=True) -> str          # item template
catalog.set_published(item_template: str, option: str, published: bool, *, owner: str) -> None
orders.record_shipment(sales_order: str, *, carrier, awb, tracking_url, status, events) -> str
```

- `made_to_order=True` creates non-stock items: checkout skips the stock check and the storefront
  never shows them sold out.
- `set_published(..., owner=app_name)` records who unpublished; an app only republishes what it
  unpublished itself.
- `record_shipment` writes a bwh_shipping **Shipping Request** against the order, so the dashboard's
  progress, order status (Shipped → Delivered) and the customer's order page show tracking.

---

## 4. Build kit (`@commera/extension-kit`)

```
my_app/                          # repo root
├── package.json                 # "build" + "dev" scripts
├── yarn.lock                    # committed: bench runs `yarn install --frozen-lockfile`
├── commera/                     # extension sources, one folder per module
│   ├── vite.config.js
│   └── loyalty-order-block/index.vue
└── my_app/public/commera/       # build output (gitignored)
```

```json
{
  "scripts": {
    "dev": "vite build --watch --config commera/vite.config.js",
    "build": "vite build --config commera/vite.config.js"
  },
  "devDependencies": { "@commera/extension-kit": "file:../commera/packages/extension-kit" }
}
```

```js
// commera/vite.config.js
import { defineConfig } from 'vite'
import commera from '@commera/extension-kit/vite'

export default defineConfig({ plugins: [commera()] })
```

- Every folder under `commera/` with an `index.vue` becomes an entry named after the folder, written
  to `<app>/public/commera/<module>.js` (fixed name; shared chunks are hashed).
- `vue`, `frappe-ui` and `@commera/admin` are external.
- The build stamps the kit's API version into each module; the dashboard refuses modules it does not
  support and says why.
- `bench build` runs the app's `yarn build`; `bench build --app my_app` rebuilds the app alone.
  Commera is never rebuilt for an extension.

---

## 5. CLI

| Command | Does |
| --- | --- |
| `bench commera new-extension --app A --target T --module M` | Adds the builder line to `A/commera/extensions.py` and a per-target `commera/M/index.vue` template |
| `bench --site S commera extensions list [--user U]` | Every extension: app, handle, target, module URL, API version check, visible to `U` |
| `bench --site S commera extensions validate [--app A]` | Registry + build check with "did you mean" suggestions. Also runs after migrate |
| `bench --site S commera extensions types --app A` | Writes `commera/commera-env.d.ts` for editor types |

Test helper: `from commera.sdk.testing import assert_extensions_valid` — call it in the app's CI.

---

## 6. Developer lifecycle

| Stage | Shopify | Commera |
| --- | --- | --- |
| Scaffold | `shopify app init` | `bench new-app`, then `bench commera new-extension` |
| Develop | `shopify app dev` (tunnel, preview) | `bench start` + `yarn dev`; developer mode rebuilds the registry per request; **Settings → Developer** lists extensions and their last error. Webhooks via any HTTPS tunnel |
| Test | Dev Console, `app webhook trigger` | `bench run-tests --app`, `assert_extensions_valid`, kit e2e helpers |
| Ship | `shopify app deploy` (versions) | Push to git; `bench build` on deploy; FC marketplace listing |
| Install | Managed install + scopes | `install-app`. Permissions are Frappe's; `requires` gates visibility |
| Uninstall | `app/uninstalled` webhook | `uninstall-app`; extensions vanish automatically. Clean up external registrations in `before_uninstall` |
| Discover | App Store | **Settings → Installed apps → Discover**, from the FC marketplace API filtered to Commera apps |
| Billing | Billing API | FC marketplace plans; no app code |

## Open questions

- Integration settings as a card in Settings → Shipping / Payments (via `commera_shipping_providers`)
  versus the app's own `settings()` tab — both are specified; do we keep both?
- Merchant-arranged block placement (Medusa 2.17.2 moved to layouts) or fixed placement in v1.
