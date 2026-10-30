# Shipping providers

A shipping provider is a carrier that quotes rates at checkout and can book, cancel and track shipments. Commera includes Shiprocket and AfterShip. An app can add a carrier without a change to Commera.

## Add a carrier

Run this command in your app folder:

```bash
bench commera shipping-provider new Delhivery
```

The command does these steps:

1. It writes the `Delhivery Shipping Settings` Single DocType in the first module of your app. The DocType has an API key, a pickup address, a currency and a volumetric divisor.
2. It writes a controller that subclasses `commera.shipping.base_class.ShippingProviderBase`.
3. It adds `commera` to `required_apps`, sets `commera_api_version`, and registers the DocType in `hooks.py`:

```python
commera_hooks = {"shipping_providers": ["Delhivery Shipping Settings"]}
```

Then implement `get_rates` and run `bench --site <site> migrate`. The carrier shows on Settings > Integrations. When you turn it on, Commera creates a Shipping Provider Profile with the carrier's `label` as its name.

## Contract

Only `get_rates` is required. Commera finds the other capabilities from the methods that your class overrides, with `supports(capability)`.

| Method | Capability | Required | Commera calls it to |
| --- | --- | --- | --- |
| `get_rates(request)` | None | Yes | Price the delivery options at checkout. |
| `create_shipment(shipment)` | `booking` | No | Book a Shipment and buy its label. |
| `cancel_shipment(order_ref, shipment_ref, awb)` | `cancel` | No | Cancel a booking. |
| `get_tracking(awb, shipment_ref, tracking_ref)` | `tracking` | No | Sync the status of a Shipment. |
| `handle_webhook(payload, headers)` | `webhook` | No | Apply a tracking update that the carrier posts. |
| `schedule_pickup(shipment_ref, pickup_date)` | `pickup` | No | Ask the carrier to collect a parcel. |
| `generate_manifest(shipment_refs)` | `manifest` | No | Get the handover sheet. |
| `resume_booking(order_ref, shipment_ref, service_code)` | `resume` | No | Finish a booking that failed halfway. |
| `get_service_choices()` | `service_choices` | No | Import the carrier's services as delivery options. |

### Rate request

`get_rates` gets one `commera.shipping.base_class.RateRequest`:

| Field | Content |
| --- | --- |
| `origin`, `destination` | Addresses. The origin is the carrier's `pickup_address`. |
| `parcels` | One estimated box with the cart weight. |
| `items` | One `RateItem` per cart line: `item_code`, `item_name`, `product` (the template of a variant), `qty`, `weight` (kg for one unit) and `rate`. |
| `currency`, `locale` | The cart currency and the shopper's language. |
| `subtotal`, `total`, `discount` | The cart totals. |
| `customer`, `customer_group` | The shopper, when known. |
| `cod`, `declared_value` | Cash on delivery and the value to insure. |
| `timeout_seconds` | The time limit for the answer. The default is 10 seconds. |

### Rates

`get_rates` returns one dict for each service, or `[]` when the carrier does not serve the route:

```python
{
	"service_code": "express",  # Stable. Commera sends it back unchanged to create_shipment.
	"service_name": "Express",
	"amount": 120.0,  # Major units of `currency`.
	"currency": "INR",
	"description": "Signature on delivery",  # Optional
	"min_delivery_date": "2026-11-02",  # Optional. Else Commera uses transit_days.
	"max_delivery_date": "2026-11-04",  # Optional
	"transit_days": 3,  # Optional
	"phone_required": True,  # Optional. Checkout then asks for a phone on the shipping address.
}
```

A rate prices the Shipping Service with the same `service_code`. When **Offer Every Carrier Rate** is on for the Shipping Provider Profile, Commera also shows each rate that no Shipping Service covers, with the title `<carrier> <service_name>`.

Units are kg, cm and the major unit of the currency. Use `commera.shipping.units.normalise_parcel` to convert. `get_tracking` and `handle_webhook` return a `status` from `commera.shipping.status.SHIPMENT_STATUSES`.

### Errors and caching

| Carrier answer | Result at checkout | Cached for |
| --- | --- | --- |
| Rates | The rates price the options. | 15 minutes, for the same request. |
| `[]` | The options use a Shipping Rule band or their Backup Charge. | 15 minutes. |
| An exception, or an answer after `timeout_seconds` | Commera logs the error. The options use a band or their Backup Charge. | 30 seconds. |

There is no retry. A save of the carrier's settings or of its Shipping Provider Profile clears the cached rates.

To hide, rename or reorder the options at checkout, use the `delivery_options` key of `commera_hooks`.

These class attributes describe the carrier on the Integrations screen:

| Attribute | Use |
| --- | --- |
| `label` | The card title and the name of the Shipping Provider Profile. Do not change it after a site uses it. |
| `blurb` | One line under the title. |
| `docs_url` | A link to the carrier's API documentation. |
| `logo` | An image URL, such as `/assets/my_app/images/delhivery.svg`. |

Commera reads `pickup_address` and `volumetric_divisor` from the settings with `get()`. Checkout ships from `pickup_address`.

## Webhooks

Set the carrier to post to `/api/method/commera.shipping.webhook.handle?provider=<Profile name>`. The Integrations screen shows this URL. `handle_webhook` must verify that the request comes from the carrier. It returns `{}` to ignore the request, or `{"awb", "status", "event_id", "events"}`.

## Checks and failures

| When | What Commera checks | Result of a problem |
| --- | --- | --- |
| `bench migrate` and app install | Each registered DocType exists, is a Single and subclasses `ShippingProviderBase`. Each enabled profile uses a registered DocType. | The command stops with the problem. |
| App uninstall | The app's enabled profiles. | Commera disables them and logs a warning. |
| Profile save | The settings DocType is registered. | The save is refused. |
| Checkout | The carrier answers. | Commera logs the error and prices the option from a Shipping Rule band or its Backup Charge. |
| Booking, tracking | The carrier supports the action. | The action is refused with a message. |

An app that declares a different `commera_api_version` is skipped. Its carriers are not registered.

## Tests

Use `InMemoryShippingProvider` with `use_providers`. Inside the block, only the listed Shipping Provider Profiles exist, and no request goes to a carrier.

```python
from commera.shipping.providers import use_providers
from commera.shipping.testing import InMemoryShippingProvider

carrier = InMemoryShippingProvider(rates=[{"service_code": "express", "amount": 40}])
with use_providers({"Delhivery": carrier}):
    options = quote_services(origin, destination, parcels, cart)

assert carrier.rate_requests[0].items
```

- `rate_requests` holds each `RateRequest` that the carrier got.
- `fail_rates=True` makes `get_rates` raise. `delay_seconds` makes it answer late.
- `use_providers({})` means that no carrier exists. Use it when a test must not reach a real carrier.
- `use_providers` clears the cached rates when the block starts and ends.
