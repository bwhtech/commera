# Telemetry

Date: 2026-11-02
Status: **Accepted. Phases 0 to 4 ship with this change.** Modelled on Wiki's `specs/telemetry.md` and `specs/product_telemetry.md`, which follow Insights.

One row per event Commera sends to Pulse. After this spec is accepted, this file is the only definition of an event's name and properties. A new event or property lands here in the same PR as the code.

## Why

Commera sends no product telemetry. We cannot tell how many stores run, where a new merchant stops between signup and the first paid order, which payment gateways they connect, or whether stores stay alive after launch.

## How it works (shared with Frappe and Wiki)

- **Backend:** `frappe.utils.telemetry.capture(event, "commera", properties=..., interval=...)`. It is a no-op when telemetry is off and never raises. It anonymizes the user (site-salted hash), adds the site and `fc_team`, and queues the event in Redis. The `send_queued_events` scheduler job flushes the queue to Pulse. `interval="1d"` keeps one row per user per day and ignores properties.
- **Frontend:** `telemetryPlugin` / `useTelemetry()` from `@framework/ui` (`frappe/ui/src/telemetry`). It reads `boot_config` and posts straight to Pulse from the browser. With `router` passed, it sends a `pageview` with the route pattern on sites younger than 15 days.
- **Free:** `app_heartbeat` is already sent for every `/api/method/commera.*` call (throttled to once per 6 h).
- **Team profile:** `frappe.utils.telemetry.pulse.client.identify(properties)` upserts attributes on the Frappe Cloud team. Commera uses it for slow-changing store facts (country, currency) so that every event can be segmented without carrying them.

### Consent

Commera adds no setting. Telemetry is on only when all of these are true (`pulse/client.py:is_enabled`):

1. `pulse_api_key` is in site config. Frappe Cloud sets it. Self-hosted sites send nothing.
2. `developer_mode` is off, unless `pulse_force_enabled` is set.
3. System Settings `enable_telemetry` is on.

## Who is the user

Commera has two kinds of people. Pulse must only count one of them as a "user".

| Person | Where | Telemetry |
|---|---|---|
| **Merchant** (store staff) | `/commera` dashboard SPA, admin APIs | Yes. This is the product user. |
| **Shopper** | storefront, cart, checkout (mostly guests) | No events per shopper. Shopper behaviour reaches Pulse only as counts on the merchant's site, from the daily scan and from one-time milestones. |

Reason: a busy store would send thousands of shopper events a day, every guest gets the same anonymized id, and the store already logs shopper behaviour first-party in `Storefront Analytics Event` (`page_view`, `view_item`, `add_to_cart`, `begin_checkout`, `purchase`). The daily scan reads that table instead of duplicating it.

## Questions

Events exist to answer these. An event that answers no question stays in Planned.

| # | Question | Read from |
|---|---|---|
| 1 | How many stores run Commera, and how many are active weekly | `active_site`, `site_profile` as denominator |
| 2 | Where do new stores stop between install and first paid order | funnel of `store_milestone_reached.milestone` |
| 3 | How long does a store take to activate | `store_milestone_reached.days_since_install` for `first_order_paid` |
| 4 | Does the setup panel help, or do merchants skip it | `setup_step_opened`, `setup_skipped`, `setup_dismissed`, then milestones by cohort |
| 12 | Where do owners stop inside first-run onboarding, and how long does it take | `started_setup`, `completed_setup_step`, `skipped_setup_step`, `went_back_in_setup`, `left_setup`, `onboarding_completed` |
| 13 | Does the background store setup succeed, and how long do owners wait for it | `store_setup_started`, `store_setup_finished` |
| 14 | Does anyone open the accounting disclosure or override the chart of accounts | `onboarding_accounting_opened`, `store_setup_started.*_overridden` |
| 15 | What do new stores pick in onboarding: category, logo, colour, theme, cash on delivery, guest checkout | `onboarding_completed` |
| 16 | Do owners look at their Frappe Cloud billing from Commera | `billing_opened` |
| 5 | Which payment gateways do stores connect, and do they get paid through them | `payment_gateway_enabled`, `site_profile.gateway_*`, `site_profile.paid_orders_30d_by_gateway` |
| 6 | Do shoppers who reach the gateway pay | `site_profile.gateway_checkouts_30d` against `site_profile.gateway_orders_paid_30d` |
| 7 | Prepaid or cash on delivery: what do stores and shoppers pick | `site_profile.orders_cod_30d`, `orders_prepaid_30d`, `cod_enabled` |
| 8 | Is the storefront visited, and does it convert | `site_profile.sessions_30d`, `checkout_sessions_30d`, `orders_30d` |
| 9 | Does a store stay alive after its first order | `site_profile.orders_7d`, `last_order_days_ago`, `active_site` |
| 10 | Which features earn their maintenance: discounts, reviews, pages, themes, plugins, shipping carriers, analytics integrations | config events and `site_profile` counts |
| 11 | Does behaviour change after an upgrade | every event by `app_version` |

## Activation

The funnel a new store goes through. It starts with first-run onboarding (`started_setup`, `store_setup_finished`, `onboarding_completed`, see First-run onboarding). After that, each step is one `store_milestone_reached` with that `milestone`. Sites that were set up before onboarding existed are marked onboarded by a patch and send no onboarding events; `active_site` counts them.

| Order | `milestone` | Fires when | Owner of the fact |
|---|---|---|---|
| 1 | `first_product_created` | the first product is created (a Style Attribute Configurator: one dashboard product, not one Item per size) | product count goes from 0 to 1 |
| 2 | `first_product_published` | the first variant is published to the storefront | published count goes from 0 to 1 |
| 3 | `payment_method_enabled` | the first gateway or cash on delivery is turned on | no other payment method was enabled before |
| 4 | `shipping_configured` | the first shipping rule is saved or the first carrier integration is enabled | rule or carrier count goes from 0 to 1 |
| 5 | `theme_customized` | a theme is activated, saved or its layout published, and the store no longer looks as installed: the active theme is not Summer Theme, or it has a published layout, or its settings differ from the defaults | customized goes from false to true |
| 6 | `first_gateway_checkout` | the first shopper is sent to a payment gateway (`open_checkout` returns a gateway redirect) | open gateway Payment Request count goes from 0 to 1 |
| 7 | `first_order_placed` | the first store Sales Order is placed (`place_order`) | store order count goes from 0 to 1 |
| 8 | `first_order_paid` | the first store order is paid (`order_paid` in `plugin_events`) | paid store order count goes from 0 to 1. Paid = billed 100% with no unpaid invoice (`plugin_events.get_settled_orders_query`), because `order_paid` rows are deleted after 14 days |
| 9 | `tenth_order_paid` | the tenth paid store order | paid count reaches 10 |

**Definitions.**

- **Onboarded** = `onboarding_completed`.
- **Set up** = `first_product_created`, `payment_method_enabled` and `shipping_configured` all reached. This is the same list the setup panel shows (`dashboard/src/data/firstRun.js`), read from the same server method (`get_setup_state`).
- **Activated** = `first_order_paid`, from a shopper who is not a store user, on a gateway in live mode or by cash on delivery.
- **Retained** = at least one paid order in each of the 4 weeks after activation (read from `site_profile`).

Milestones are derived from the database at the moment the count changes from 0 to 1. Commera stores no "milestone sent" flag, so there is one owner for the fact. A milestone can fire twice only if the data is deleted and created again, which is acceptable.

Two more properties go on every milestone so the funnel can be read without joins:

- `days_since_install`: days since Commera was installed on the site, read from the creation of the `Commera` Module Def (the Installed Application row is recreated on reinstall).
- `source`: `person`, `demo_data`, `import`, `plugin`. Only `person` counts for activation. Demo data installers and the CSV import run under `commera.telemetry.data_source(...)`, which sets `frappe.flags.commera_telemetry_source`. A milestone fires once, so a store whose first product came from demo data never sends a `person` `first_product_created`.

## Rules

- Name: `<object>_<verb>`, past tense, snake_case. Variation goes in properties, never in the name (`payment_gateway_enabled {gateway: stripe}`, not `stripe_enabled`).
- Property keys are flat. Values are enums, booleans, small counts or buckets.
- Never send product names, SKUs, prices, order values, customer names, emails, addresses, domains, theme or page titles. Count them or bucket them, never name them. Money goes out only as a bucket (`value_bucket`), never as an amount.
- Enum values come from a fixed registry in code (gateway slugs from `PAYMENT_GATEWAYS`, carrier slugs from the shipping registry, built-in theme names). A value outside the registry is sent as `other`, so a custom plugin or theme name never leaks.
- The user is always the anonymized id that Frappe and the Pulse client add. Commera never passes a user.
- Backend is the default for anything that changes data. The frontend sends only what the server never sees (setup panel clicks, welcome screen, command palette).
- The frontend plugin is installed only in the `/commera` dashboard, only for a signed-in user. The storefront sends nothing to Pulse.
- Facts about the store come from the daily scan, never from a request path.
- Backend sends through `commera.telemetry.capture(event, interval=None, **props)`. Work done only to build an event goes in a function wrapped with `@telemetry_event`, which runs only when telemetry is on and swallows every error. Frontend sends through `dashboard/src/telemetry.js` `useTelemetry().capture(event, props)`. Both add the shared properties and swallow every error. Telemetry never fails the action it reports on.

## Properties on every event

| Property | Source | Value |
|---|---|---|
| `app_version` | `commera.__version__`; frontend from the boot key `telemetry` | e.g. `1.0.0` |
| `hosting` | `commera_cloud` installed → `commera_cloud`, else `fc_team` set → `frappe_cloud`, else `self_hosted` | enum |
| site, user, team, timestamp | Pulse client | automatic |

## Events

### Presence

| Event | Half | Fires when | Properties | Question |
|---|---|---|---|---|
| `active_site` | backend, `interval="1d"` | `www/commera.py:get_context` serves the dashboard to a signed-in user | | 1 |
| `pageview` | frontend | a router navigation, on sites younger than 15 days. Sent by the framework plugin itself, so it carries no shared properties | `route`: the matched route pattern, never the URL | 1, 4 |

### First-run onboarding

The owner's first visit opens `OnboardingFlow` instead of the dashboard (steps in `dashboard/src/ia/onboardingSteps.js`: `you`, `store`, `brand`, `theme`, `selling`, `products`, `done`). The server sends what it saves; the browser sends only the clicks the server never sees.

The funnel events use the names of Frappe's own setup wizard (`frappe/desk/page/setup_wizard/setup_wizard.js`), as Raven's do, with app `commera`. One funnel query then reads Frappe, Raven and Commera alike. The browser does not send them to Pulse itself: it posts them to `onboarding.record_setup_event` (`dashboard/src/data/setupFunnel.js`), which passes on only the events below, known step names and whole numbers. That also lets `left_setup` go out with `keepalive` while the page closes. A site with telemetry off sends no request: the boot key `telemetry.enabled` says so.

| Event | Half | Fires when | Properties | Question |
|---|---|---|---|---|
| `started_setup` | frontend, through the server | `OnboardingFlow` has loaded | `step`: the step it opens at. `resumed`: bool, a reload resumed past `you`. `total_steps` | 12 |
| `completed_setup_step` | frontend, through the server | Continue saves a step and moves on | `step`, `step_number` (1-based), `total_steps`, `duration_seconds`: time on the step, save included | 12 |
| `skipped_setup_step` | frontend, through the server | Skip on an optional step (`brand`, `products`) | as `completed_setup_step` | 12 |
| `went_back_in_setup` | frontend, through the server | Back on a step | `from_step`, `to_step` | 12 |
| `left_setup` | frontend, through the server, `keepalive` | the page closes or reloads before Go to dashboard | `step`: the step on screen. `duration_seconds` on it | 12 |
| `onboarding_accounting_opened` | frontend, through the server | the accounting line on the `store` step opens | | 14 |
| `products_import_opened` | frontend | the CSV import dialog opens | `surface`: `onboarding`, `products`, `search` (the command palette) | 2, 10 |
| `store_setup_started` | backend | `start_store_setup` queues ERPNext's setup (not when it is already done or running) | `country`: ISO code. `currency`: ISO code. `chart_of_accounts`: `standard`, `standard_with_numbers`, `other`. `chart_overridden`, `fiscal_month_overridden`, `abbr_overridden`: bool, the owner changed the default. `is_retry`: bool, a failed setup is started again | 13, 14 |
| `store_setup_finished` | backend | `run_store_setup` ends | `outcome`: `done`, `failed`. `duration_bucket`: `lt_30s`, `30_60s`, `60_120s`, `gt_120s`. `error_kind`: exception class bucket on failure, never the message | 13 |
| `onboarding_completed` | backend | `complete_onboarding` | `store_category`: the category enum, else `other`. `has_logo`, `custom_colour`: bool. `theme`: built-in theme name, else `custom`. `cod_enabled`, `guest_checkout_enabled`: bool. `minutes_since_install`: bucket `lt_5`, `5_15`, `15_60`, `gt_60` | 12, 15 |

### Setup panel (frontend)

| Event | Half | Fires when | Properties | Question |
|---|---|---|---|---|
| `setup_step_opened` | frontend | a merchant clicks a step in `SetupPanel` | `step`: `product`, `payments`, `shipping`, `theme`. `surface`: `panel`. `steps_done`: 0 to 4 | 4 |
| `setup_dismissed` | frontend | `dismissSetup()` | `steps_done` | 4 |
| `setup_skipped` | frontend | `skipSetup()` | `steps_done` | 4 |

The setup panel is still a preview (it shows only with `?setup`), so these events fire only once it is turned on for every store. `steps_done` comes from `onboarding.get_setup_state`, one server method that returns the four steps as booleans. The setup panel and the milestones both read the same facts, so they always agree.

### Billing (frontend)

Plan changes and payments happen inside Frappe Cloud's own panel, which Frappe Cloud already records. Commera sends only how owners reach it.

| Event | Half | Fires when | Properties | Question |
|---|---|---|---|---|
| `billing_opened` | frontend | Settings → Billing opens | `surface`: `settings`, `trial_card`. `trial`: bool, the site is or was on a trial | 16 |

### Activation (backend)

| Event | Half | Fires when | Properties | Question |
|---|---|---|---|---|
| `store_milestone_reached` | backend | see Activation | `milestone`, `days_since_install`, `source`. Plus on `payment_method_enabled`, `first_gateway_checkout` and `first_order_paid`: `payment_method` (gateway slug or `cod`). On `first_order_paid`: `is_guest` | 2, 3, 5 |

### Store configuration (backend)

| Event | Half | Fires when | Properties | Question |
|---|---|---|---|---|
| `payment_gateway_enabled` | backend | `save_payment_integration` with `enabled=1` on a gateway that was off | `gateway`: `razorpay`, `stripe`, `telr`, `tabby`, `other`. `live_mode`: bool, where the gateway settings have a test flag | 5 |
| `payment_gateway_disabled` | backend | the same method turns a gateway off | `gateway`. `days_enabled`: days since the gateway was last saved | 5 |
| `payment_gateway_save_failed` | backend | `save_integration` throws | `gateway`. `reason`: `missing_fields`, `other` (no gateway checks credentials on save yet) | 5 |
| `cod_toggled` | backend | cash on delivery is turned on or off in Settings → Payments | `enabled`: bool | 7 |
| `shipping_integration_enabled` | backend | `save_shipping_integration` turns a carrier from off to on | `carrier`: slug from the shipping registry, else `other` | 10 |
| `shipping_rule_saved` | backend | `save_shipping_rule` | `bands`: count. `has_free_shipping`: bool | 10 |
| `theme_applied` | backend | the active storefront theme changes | `theme`: built-in theme name, else `custom` | 10 |
| `storefront_page_created` | backend | a Shop Web Page is inserted | | 10 |
| `discount_created` | backend | a Commera Discount is inserted | `type`: the discount type enum. `has_code`: bool | 10 |
| `analytics_integration_enabled` | backend | GA4, Meta Pixel or a custom script is enabled | `provider`: `ga4`, `meta`, `custom_script` | 10 |
| `plugin_installed` | backend | an app that declares storefront hooks is installed (`after_app_install`) | `plugin`: slug from `commera.telemetry.configuration.PLUGINS`, else `other` | 10 |
| `products_imported` | backend | an import finishes | `rows_bucket`: `lt_10`, `10_100`, `100_1000`, `gt_1000`. `outcome`: `ok`, `partial`, `failed` | 2, 10 |

### What a store holds

One event a day from `commera/telemetry/scan.py`, sent from the daily scheduler. It answers for every store, including stores nobody opened today, and it is the denominator for every other event. It reads Commera's own tables and sends nothing when telemetry is off. If it grows past the 4096-byte property cap, split it the way Insights does (`site_profile`, `site_commerce`).

| Event | Half | Fires when | Question |
|---|---|---|---|
| `site_profile` | backend | the daily scheduler job | 1, 2, 5 to 10 |

| Group | Property | Value |
|---|---|---|
| Identity | `site_age_days`, `commera_installed_days_ago` | days |
| Timeline | `first_product_days_ago`, `first_gateway_days_ago`, `first_order_days_ago`, `first_paid_order_days_ago`, `last_order_days_ago` | days, null when it never happened |
| Catalogue | `products`, `products_published`, `variants`, `collections` | counts |
| Payments | `gateway_razorpay`, `gateway_stripe`, `gateway_telr`, `gateway_tabby`, `cod_enabled` | booleans |
| Shipping | `shipping_rules`, `shipping_carriers_enabled`, `pickup_locations` | counts |
| Storefront | `theme`, `storefront_pages`, `plugins_enabled`, `analytics_integrations` | built-in name or `custom`; counts |
| Features | `discounts_active`, `reviews_30d`, `wishlist_items`, `oos_subscriptions`, `guest_checkout_enabled` | counts, booleans |
| Traffic (from `Storefront Analytics Event`) | `sessions_30d`, `product_view_sessions_30d`, `add_to_cart_sessions_30d`, `checkout_sessions_30d` | counts |
| Checkout | `gateway_checkouts_30d` (gateway Payment Requests opened), `gateway_orders_paid_30d`, `orders_cod_30d`, `orders_prepaid_30d` | counts |
| Orders | `orders_7d`, `orders_30d`, `orders_cancelled_30d`, `guest_order_share_bucket` | counts, bucket |
| Value | `gmv_30d_bucket`, `aov_bucket` | buckets in the store currency band, never an amount |
| People | `staff_users`, `staff_active_30d`, `customers` | counts |

### Team profile (`identify`)

Sent from the daily scan when a value changes. Only on Frappe Cloud, where `fc_team` is set.

| Property | Value |
|---|---|
| `store_country` | ISO country code of the store company |
| `store_currency` | ISO currency code |
| `commera_activated` | bool, `first_order_paid` reached |
| `catalogue_size_bucket` | `lt_10`, `10_100`, `100_1000`, `gt_1000` |

## Plan

All phases ship together, stacked on the onboarding and billing change (PR #375).

### Phase 0: prerequisites

1. Link `@framework/ui` into `dashboard/` (`package.json` link and `frameworkUI()` in `vite.config`), as Wiki did. The dashboard is on `frappe-ui` 1.0.2, which is above the `>=1.0.0-beta.63` floor.
2. Add `onboarding.get_setup_state` and wire `firstRun.js` `done` to it.

### Phase 1: tracer bullet

- `commera/telemetry/`: `capture`, `default_properties` and the bucket helpers in `__init__.py`; `milestones.py`, `onboarding.py`, `configuration.py`, `scan.py`. The setup facts the milestones and the setup panel share are in `commera/setup_state.py`.
- `active_site` in `www/commera.py:get_context`.
- `dashboard/src/telemetry.js` and `app.use(telemetryPlugin, { app_name: 'commera', router })` once signed in, which gives `pageview`.
- Done when one `active_site` is in the server queue and one `pageview` leaves the browser with `app: "commera"`. Verify on `commera.localhost` with `pulse_api_key` and `pulse_force_enabled` set; Playwright stubs `boot_config` and the Pulse client.

### Phase 2: activation funnel

`store_milestone_reached` for all nine milestones, the onboarding events and the payment gateway events. One unit test per milestone, including "demo data does not count".

### Phase 3: daily scan and team profile

`site_profile` and `identify`.

### Phase 4: configuration events

The rest of "Store configuration".

## Decisions

1. **Activation** is `first_order_paid`. `first_order_placed` is also sent, so a COD-heavy store can be read on the placed step.
2. **Test orders.** `live_mode` is sent where the gateway settings have a test flag, and left out where they do not. Activation is not filtered on it yet; the funnel can filter by `live_mode` later.
3. **Signup** is Commera Cloud's to send, later. The funnel here starts at `started_setup`.
4. **Headless storefronts** are not split by channel yet.
5. **Money buckets** use fixed bands in the store currency (`lt_100` to `gt_1m`). Compare stores across currencies with the team's `store_currency`.
6. **Shopify import** sends no `products_imported` and does not set the `import` source yet. It lands with that import.

## Not tracked

- Any per-shopper event. Shopper behaviour reaches Pulse only as counts.
- Names, SKUs, prices, amounts, emails, addresses, domains, page or theme titles. They are counted or bucketed, never named.
- Anything on a site where telemetry is off.
