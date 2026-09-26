# Commera Apps — Example: Printful (`print2commera`)

Spec 3 of 4. A complete app built on the [developer API](01-developer-api.md) and the
[platform](02-platform-implementation.md): a port of the Medusa plugin
[print2medusa](https://github.com/legenki/print2medusa) (0.9.7, MIT), which connects a store to
Printful's print-on-demand service. It is the reference app and the acceptance test for specs 1 and 2:
every feature below must be buildable without touching Commera's source.

Status: draft.

## What it does

| Feature | Trigger | Commera surface used |
| --- | --- | --- |
| Catalog sync | **Sync from Printful** or nightly job | `commera.sdk.catalog`, `PRODUCT_INDEX` action, `APP_PAGE` |
| Stock and removals | During sync | `catalog.set_published(owner="print2commera")` |
| Send orders to Printful | `commera_order_paid` (or `_placed` for COD, configurable) | Order hooks |
| Cancellation guard | `commera_before_order_cancel` | Order hooks |
| Live shipping rates | Checkout | bwh_shipping carrier + `commera_shipping_providers` card |
| Shipment tracking | Printful webhook | `commera.sdk.orders.record_shipment` |
| Order economics | On create and on each webhook | `ORDER_DETAILS` block |
| Bundles | Order time | ERPNext Product Bundle packed items |
| Admin page | Sidebar **Printful** | `NAV_LINK` + `APP_PAGE` |

## Mapping from print2medusa

| Medusa | print2medusa | print2commera |
| --- | --- | --- |
| Plugin options / env vars | `apiToken`, `storeId`, `webhookSecret`, `markupPercent`, … | Single **Printful Settings** (`Password` fields for secrets) |
| Module models (5 tables) | Links, sync log, webhook events | DocTypes below; custom fields on Item / Style Attribute Variant |
| Subscribers `payment.captured`, `order.placed` | Create Printful order | `commera_order_paid` / `commera_order_placed` + `send_cod_orders` setting |
| Workflows | Sync, create order, apply status | Python in one transaction + `frappe.enqueue` |
| Scheduled jobs | Nightly sync, webhook retry | `scheduler_events` cron |
| Fulfillment provider | Live rates | `PrintfulShippingSettings(ShippingProviderBase)` |
| Webhook route + middleware | `/hooks/printful/<secret>` | Guest whitelisted method + `rate_limit` |
| `manage_inventory: false` | POD is made to order | `upsert_product(made_to_order=True)` |
| Admin route + 2 widgets | Page, product-list panel, order panel | `APP_PAGE`, `PRODUCT_INDEX` action, `ORDER_DETAILS` block |
| `admin-bundle.test.ts` | Guards a server import blanking the admin | Not needed: Python server, per-extension error boundary |

## Layout

```
print2commera/
├── package.json  yarn.lock
├── commera/
│   ├── vite.config.js
│   ├── printful-page/index.vue
│   └── printful-order-block/index.vue
└── print2commera/
    ├── hooks.py
    ├── commera/extensions.py      # get_extensions()
    ├── api.py                     # whitelisted methods for the dashboard
    ├── client.py                  # Printful REST client (Integration Request logging)
    ├── sync.py  orders.py  webhooks.py  carrier.py
    └── printful/doctype/          # Printful Settings, Order Link, Sync Log, Webhook Event,
                                   # Printful Shipping Settings
```

## Registration

```python
# print2commera/hooks.py
required_apps = ["bwhtech/commera", "bwhtech/bwh_shipping"]

commera_extensions = ["print2commera.commera.extensions.get_extensions"]
commera_order_placed = ["print2commera.orders.on_order_placed"]
commera_order_paid = ["print2commera.orders.on_order_paid"]
commera_before_order_cancel = ["print2commera.orders.before_cancel"]
commera_shipping_providers = ["print2commera.carrier.provider_card"]

scheduler_events = {
    "cron": {
        "0 3 * * *": ["print2commera.sync.nightly"],
        "*/5 * * * *": ["print2commera.webhooks.retry_due_events"],
    }
}

before_uninstall = "print2commera.install.before_uninstall"  # custom fields, Printful webhook
```

```python
# print2commera/commera/extensions.py
from commera.sdk.extensions import Target, action, app_page, block, nav_link, settings

from print2commera.api import start_sync
from print2commera.orders import is_printful_order


def get_extensions():
    return [
        nav_link("Printful", icon="printer", page="printful"),
        app_page("printful", module="printful-page", requires="Printful Settings"),
        block(Target.ORDER_DETAILS, module="printful-order-block",
              requires="Printful Order Link", condition=is_printful_order),
        action(Target.PRODUCT_INDEX, "Sync from Printful",
               method=start_sync, requires="Printful Sync Log"),
        settings("Printful Settings"),
    ]
```

## Data model

| DocType / field | Key fields |
| --- | --- |
| **Printful Settings** (Single) | `api_token` (Password), `store_id`, `webhook_secret` (Password, generated), `auto_submit_orders`, `allow_partial_orders`, `markup_percent`, `sync_stale_minutes` (60), `on_discontinued`, `on_removed_from_printful`, `send_cod_orders` (When placed / **When paid**), `block_cancel_in_production` (Check) |
| **Printful Order Link** | `autoname: field:sales_order` (the claim), `printful_order_id`, `status`, `cost_total`, `retail_total`, `margin` (Currency), `error_message`, `last_attempt_at` |
| **Printful Sync Log** | `status`, `started_at`, `heartbeat_at`, `products_*` counters, `error_message`, `cleared_by_operator` |
| **Printful Webhook Event** | `event_id` (unique), `type`, `printful_order_id`, `payload` (JSON), `status`, `attempts`, `next_retry_at` |
| **Printful Shipping Settings** (Single, carrier) | Rate cache TTLs; linked from a Shipping Provider Profile |
| Item custom fields | `printful_sync_variant_id` (unique), `printful_availability_status` |
| Style Attribute Variant custom fields | `printful_sync_product_id`, `printful_design` (JSON) |

## Behaviour

### Orders

```python
# print2commera/orders.py
def on_order_paid(sales_order: str):
    if cod(sales_order) and settings().send_cod_orders == "When placed":
        return  # already sent on placement
    create_printful_order(sales_order)

def on_order_placed(sales_order: str):
    if cod(sales_order) and settings().send_cod_orders == "When placed":
        create_printful_order(sales_order)

def create_printful_order(sales_order: str):
    if not has_printful_lines(sales_order):
        return
    try:
        frappe.get_doc({"doctype": "Printful Order Link", "sales_order": sales_order,
                        "status": "Claimed"}).insert(ignore_permissions=True)
        frappe.db.commit()  # the claim is durable before Printful is called
    except frappe.DuplicateEntryError:
        return
    # expand Product Bundle packed_items; POST /orders (confirm = auto_submit_orders);
    # store cost, retail and margin; on an unknown outcome keep the claim and record the error

def before_cancel(sales_order: str) -> str | None:
    link = frappe.db.get_value("Printful Order Link", sales_order, ["status"], as_dict=True)
    if not link or link.status in ("Claimed", "Draft", "Canceled"):
        return None
    if settings().block_cancel_in_production:
        return _("Printful is already producing this order.")
    cancel_at_printful(sales_order)  # Printful refuses once fulfilment starts; surfaced as an error
    return None
```

Hooks run after commit, once, as a system user (spec 2 §1.4), so this app needs none of the
`on_submit` / `enqueue_after_commit` / COD-draft workarounds that raw `doc_events` would.

### Catalog sync

- `start_sync()` (whitelisted, POST): `has_permission("Printful Sync Log", "create")`; claim a run
  (row-lock Printful Settings `for_update`, refuse while a run with a fresh heartbeat exists — MariaDB
  has no partial unique index); `frappe.enqueue(queue="long", timeout=3600, enqueue_after_commit=True)`;
  return `{"message": _("Sync started")}` (the declarative action toasts it).
- The job maps each Printful sync product to `catalog.upsert_product(external_id=…,
  made_to_order=True, …)`: one Style Attribute Variant per colour, one Item per size, prices with
  `markup_percent`, Printful mockups as images. Heartbeat + counters every few products.
- Stock / removal: after a **full** sync, `catalog.set_published(…, False, owner="print2commera")` for
  colours with every size unavailable or removed; republish only what this app unpublished.

### Live rates

`PrintfulShippingSettings(Document, ShippingProviderBase).get_rates` reads `parcel["items"]`, maps
item codes to `printful_sync_variant_id`, returns `[]` for carts with no Printful lines, and serves a
fresh cache → stale cache → `[]` (bwh_shipping then uses each Shipping Service's Backup Charge).
`get_service_choices` lists Printful's methods for Commera's **Import from carrier**. The booking
methods raise "Printful ships this order itself" pending a rates-only mode in bwh_shipping.
`provider_card()` returns `{slug: "printful", label: "Printful", settings_doctype: "Printful Shipping
Settings", …}` so the carrier gets a card in Settings → Shipping.

### Webhooks

- `POST /api/method/print2commera.webhooks.printful?token=<secret>` — `allow_guest`, `methods=["POST"]`,
  `rate_limit(120/min, ip_based)`. Printful v1 sends no custom headers, so the secret is in the query
  string (logged by nginx by default; **Rotate secret** re-registers).
- Store the event (unique `event_id` absorbs redeliveries), answer 200, enqueue `apply_event` after
  commit. Retry sweep every 5 minutes with backoff; abort a sweep after 5 consecutive failures.
- `apply_event` re-reads `GET /orders/{id}` (the payload is only a trigger), serialises per order with a
  `for_update` read of the Printful Order Link, refreshes cost/margin, and calls
  `commera.sdk.orders.record_shipment(…)` per parcel, so order status and customer tracking move
  with no extension code.

## Dashboard

- **Printful page** (`printful-page`): `AppPageHeader` with **Sync now**; panels for Sales (calls
  Printful; outage → empty panel), Webhook health (local rows only), Recent syncs (`usePolling` every
  3 s while running), Stuck-sync recovery (frappe-ui `Dialog`, typed confirmation, server re-checks the
  heartbeat), Design parameters, Mockup prompts, Bundles. Sub-routes via `navigate('syncs')` etc.
- **Order block** (`printful-order-block`): `useMethodRead('print2commera.api.get_order_panel',
  { params: { sales_order: resource.name } })`; `ExtensionCard` with `StatusBadge`, cost / retail /
  margin through `money()` (margin hidden when currencies differ). Renders nothing when there is no
  link, although `condition=is_printful_order` normally hides it first.
- **Sync from Printful** and **Printful Settings**: declarative, no JavaScript.

## Tests (acceptance for specs 1 and 2)

| Test | Proves |
| --- | --- |
| `assert_extensions_valid("print2commera")` | Registration API and validation |
| Insert Printful Order Link twice → `DuplicateEntryError` | Idempotent order claim |
| Same webhook twice → one event row | Redelivery absorbed |
| Two sync claims with a live heartbeat → second refused | One sync at a time |
| COD order placed then shopper-cancelled → no Printful call | Order hooks never leak a cancelled draft |
| Made-to-order item with zero stock checks out | Made-to-order rule |
| Cart with Printful items gets a live quote | Parcel item lines |
| e2e: sidebar link → page → order block renders; broken module shows a failure card | Dashboard runtime + error boundary |

## Install

```bash
bench get-app https://github.com/<owner>/print2commera
bench --site shop.example.com install-app print2commera
```

Then: Settings → Printful (token, store ID) → Printful page → **Register webhook** → Settings →
Delivery options → **Import from carrier** → Products → **Sync from Printful**.
