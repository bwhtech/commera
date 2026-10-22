# Webhooks

A **Commera Webhook** posts Commera events to a URL, such as a headless storefront that refreshes its cached pages. It uses the same event queue as plugin `commera_events` handlers, so events are batched per transaction, sent after the commit, and retried after 1, 5, 30, 120 and 360 minutes.

## Set up a webhook

In the desk, open **Commera Webhook** and add a record:

| Field | Value |
| --- | --- |
| Title | A unique name, for example `Storefront` |
| URL | The receiving endpoint, for example `https://shop.example.com/api/webhooks/commera` |
| Secret | A random string that the receiver also knows |
| Events | The events to send |

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

Check the signature against the raw body before you parse it. Delivery is at least once: when one webhook fails, the event is sent again to every webhook that wants it, so drop an event id that you already handled.

## Storefront events

| Event | When | `data` |
| --- | --- | --- |
| `product_updated` | An Item, a product option, a selling Item Price or a product's publishing changes, or an option is deleted | `item_code`, `changed` (`details`, `options`, `published`, `price`), `handles` |
| `inventory_changed` | Stock moves in the store warehouse, or an order reserves or releases it | `warehouse`, `actual_qty`, `available_qty`, `handles`; the item code is `reference_name` |
| `collection_updated` | An Item Group is saved or deleted | `handle` |
| `page_updated` | A Shop Web Page is saved or deleted | `route` |
| `menu_updated` | The menu, a footer section or Commera Settings is saved | Nothing |

`handles` are the routes of the products the change touches, published or not. A webhook can also subscribe to the order, cart and discount events that plugins receive.
