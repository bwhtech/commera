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
| `get_rates(origin, destination, parcels, cod, declared_value)` | None | Yes | Price the delivery options at checkout. |
| `create_shipment(shipment)` | `booking` | No | Book a Shipping Request and buy its label. |
| `cancel_shipment(order_ref, shipment_ref, awb)` | `cancel` | No | Cancel a booking. |
| `get_tracking(awb, shipment_ref, tracking_ref)` | `tracking` | No | Sync the status of a Shipping Request. |
| `handle_webhook(payload, headers)` | `webhook` | No | Apply a tracking update that the carrier posts. |
| `schedule_pickup(shipment_ref, pickup_date)` | `pickup` | No | Ask the carrier to collect a parcel. |
| `generate_manifest(shipment_refs)` | `manifest` | No | Get the handover sheet. |
| `resume_booking(order_ref, shipment_ref, service_code)` | `resume` | No | Finish a booking that failed halfway. |
| `get_service_choices()` | `service_choices` | No | Import the carrier's services as delivery options. |

`get_rates` returns one dict for each service, or `[]` when the carrier does not serve the route:

```python
{"service_code": "express", "service_name": "Express", "amount": 120.0, "currency": "INR"}
```

The `service_code` is the key that links a rate to a Shipping Service. Commera sends it back unchanged to `create_shipment`.

Units are kg, cm and the major unit of the currency. Use `commera.shipping.units.normalise_parcel` to convert. `get_tracking` and `handle_webhook` return a `status` from `commera.shipping.status.SHIPMENT_STATUSES`.

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

assert carrier.rate_requests
```

`use_providers({})` means that no carrier exists. Use it when a test must not reach a real carrier.
