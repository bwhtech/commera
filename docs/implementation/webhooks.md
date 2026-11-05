# Webhooks

A **Commera Webhook** posts Commera events to a URL, such as a headless storefront that refreshes its cached pages or an app that syncs orders. It uses the same event queue as plugin `commera_events` handlers, so events are batched per transaction, sent after the commit, and retried after 1, 5, 30, 120 and 360 minutes.

Source of truth: `commera/webhooks.py` (delivery, signing, event list, auto turn-off), `commera/api/admin/webhooks.py` (dashboard API), and the **Commera Webhook** and **Commera Webhook Log** doctypes.

## Set up a webhook

In the dashboard, open **Settings > Webhooks** and add a webhook. Enter the receiving URL, for example `https://shop.example.com/api/webhooks/commera`, and select the events to send. A headless storefront needs the Catalogue and Storefront content events: use **Select all** on those two groups.

Commera makes the signing secret (`whsec_` and 32 hex characters) and shows it one time. Copy it into the receiving app. You can show the secret again or rotate it from the webhook page. After a rotation, update the receiving app, because Commera signs the next request with the new secret.

System Managers and Commera Admins can manage webhooks. A webhook must have at least one event.

The URL must use `https://` and point to a public address. Commera refuses `localhost`, private networks and link-local addresses such as the cloud metadata service, both when you save the webhook and before each request, because a name can point somewhere else later. Commera does not follow redirects: a redirect counts as a failed attempt. For local development, set `commera_webhooks_allow_local_urls` to `1` in the site config. Then `http://` and private addresses are allowed, for example `http://127.0.0.1:3100/api/webhooks/commera`.

Commera records an event only while a plugin or an enabled webhook wants it. A site without webhooks records nothing extra.

## Request

Each event is a `POST` with a JSON body:

```json
{
  "id": "product_updated-4f1c9a2b7e",
  "event": "product_updated",
  "reference_doctype": "Item",
  "reference_name": "BRAKE-PADS",
  "created_at": "2026-10-22 10:15:03.120000",
  "data": {"item_code": "BRAKE-PADS", "changed": ["price"], "handles": ["brake-pads-black"]}
}
```

| Header | Value |
| --- | --- |
| `X-Commera-Hmac-Sha256` | The base64 HMAC-SHA256 of the raw body, with the webhook secret as the key |
| `X-Commera-Event` | The event name |
| `X-Commera-Event-Id` | The event id |

Check the signature against the raw body before you parse it. Reply with a 2xx status in less than 10 seconds. Any other status, a timeout or a connection error is a failed attempt.

Delivery is at least once. A retry goes only to the webhooks that did not get the event yet, but a replay sends it again, so drop an event id that you already handled.

## Logs

Each webhook keeps one log row per event, with the status, attempts, response code, duration, error, the exact body and the signature that Commera sent. Commera deletes log rows after 30 days, and deletes all the rows of a webhook when you delete the webhook.

| Status | Meaning |
| --- | --- |
| Done | The receiver replied with a 2xx status |
| Retrying | The last attempt failed. `next_retry_at` shows the next attempt |
| Failed | All the retries failed, or Commera turned the webhook off |

**Retry now** sends every Retrying event of the webhook again on the next queue run.

## Replay and test

**Replay** posts the logged body again, now, to the current URL of the webhook. Commera signs it with the current secret and sends the same event id. The new log row shows the row that it replays.

**Send test** posts a `webhook_test` event now:

```json
{"id": "webhook_test-4f1c9a2b7e", "event": "webhook_test", "reference_doctype": null, "reference_name": null, "created_at": "2026-11-04 10:15:03.120000", "data": {"test": true}}
```

Replays and tests do not retry, and do not count towards the failure limit.

## Auto turn-off

When a webhook has 10 failed attempts in 24 hours, Commera turns it off. The 24 hours start at the first failed attempt; after 24 hours, the next failed attempt starts a new count. When Commera turns a webhook off, it sets **Turned Off At** and marks the Retrying log rows of the webhook as Failed. Commera then sends nothing to the webhook.

Fix the receiver, then turn the webhook on. This clears the failure count and **Turned Off At**. Use **Replay** for the events that the receiver missed.

## Events

| Event | When | `data` |
| --- | --- | --- |
| `order_placed` | A shopper completes checkout | The order snapshot |
| `order_paid` | Payment is captured, including cash on delivery | The order snapshot |
| `order_fulfilled` | The carrier picks up the parcel | The order snapshot |
| `order_delivered` | The carrier confirms delivery | The order snapshot |
| `order_cancelled` | The order is cancelled | The order snapshot |
| `order_refunded` | All or part of the order is refunded | The order snapshot, `payment_entry`, `amount` |
| `order_returned` | All or part of the order comes back | The order snapshot, `status`, `partial` |
| `order_updated` | A submitted store order is saved, or its status changes | The order snapshot, `status` |
| `product_updated` | An Item, a product option, a selling Item Price or a product's publishing changes, or an option is deleted | `item_code`, `changed` (`details`, `options`, `published`, `price`), `handles` |
| `inventory_changed` | Stock moves in the store warehouse, or an order reserves or releases it | `warehouse`, `actual_qty`, `available_qty`, `handles`; the item code is `reference_name` |
| `collection_updated` | An Item Group is saved or deleted | `handle` |
| `page_updated` | A Shop Web Page is saved or deleted | `route` |
| `menu_updated` | The menu, a footer section or Commera Settings is saved | Nothing |

The order snapshot is `customer`, `currency`, `grand_total`, `payment_mode`, `docstatus`, `shipping_address` and `discounts`. `handles` are the routes of the products the change touches, published or not.

`order_updated` fires one time for each save and one time for each new status.

`cart_created` and `discount_used` go to plugins only, not to webhooks.
