# Payment gateways

A payment gateway opens a checkout session, reports the payment status, sends refunds and verifies webhooks. Commera includes Razorpay, Stripe, Telr and Tabby. An app can add a gateway without a change to Commera.

## Where the code lives

Each gateway has two parts: a connector, and a settings Single that stores its credentials.

| Location | Content |
| --- | --- |
| `bwh_payments_core` library | The contract, result models, currency helpers, four connectors, payment engine mixins, and test helpers. It has no DocTypes and no whitelisted endpoints. Commera pins it in `pyproject.toml`, so it installs with Commera. |
| `commera/payment_gateways/` | The "Payment Gateways" module: Gateway Payment Request, Gateway Refund, Payment Gateway Profile, and the four `<Name> Gateway Settings` Singles. |
| `commera/payment_gateways/connectors.py` | The registry of gateways, and the checks at migrate. |
| `commera/payment_gateways/api.py` | The webhook, webhook retry and return endpoints. |

## Add a gateway

Run this command:

```bash
bench commera payment-gateway new Tamara
```

The folder that you run it in sets what it writes:

| Where you run it | What it adds |
| --- | --- |
| In a clone of `bwh_payments_core` inside the bench folder | A connector and its test. It adds no Single and no hook. |
| In a Frappe app, or anywhere with `--app <app>` | A connector, its test, the `Tamara Gateway Settings` Single and the hook entry. |
| Anywhere else in the bench folder | A new app, then the same files as in a Frappe app. |

The new app has the name `commera_tamara`. To set another name, use `--app-name <app>`. The command installs the new app into the bench environment and adds it to `sites/apps.txt`.

A connector has these files:

| File | Content |
| --- | --- |
| `gateway.py` | `TamaraGateway`, the class that implements the contract. |
| `base.py` | `BaseTamaraClient`, the abstract API client, and the response models. |
| `live.py` | `LiveTamaraClient`, which calls the real API. It starts with a placeholder URL and placeholder endpoints. |
| `stub.py` | `StubTamaraClient`, an in-memory client for tests. |

A second run skips each file that exists. The command refuses the names of the gateways that Commera includes.

After the command:

1. Change `live.py` and `gateway.py` to match the gateway's API.
2. Set `description` and `docs_url` in `gateway.py`.
3. Run `bench --site <site> install-app <app>`. If the app is already on the site, run `bench --site <site> migrate`.

In the library, run `pytest` instead of step 3. A connector in the library also needs a Single and a hook entry in the app that uses it.

## Contract

A connector subclasses `bwh_payments_core.contract.PaymentGatewayBase`. All amounts are in major units, such as `12.34`. Use `to_minor_units` and `from_minor_units` from `bwh_payments_core.currency` to convert them for the gateway's API.

| Method | Required | Commera calls it to | Default |
| --- | --- | --- | --- |
| `create_session(amount, currency, reference, customer, return_url)` | Yes | Open a checkout. | None |
| `get_payment_status(session_id)` | Yes | Sync a request that is Pending. | None |
| `refund_payment(session_id, amount, currency)` | Yes | Send a refund. | None |
| `handle_webhook(payload, headers)` | Yes | Verify and read a delivery. | None |
| `cancel_session(session_id)` | No | Close an unpaid checkout, so that the cart is free again. | `False`: the session stays open. |
| `get_refund_status(session_id, refund_id)` | No | Sync a Pending refund. | `None`: the refund stays Pending. |
| `list_refunds(session_id)` | No | Find refunds that were raised outside Commera. | `None`: Commera finds none. |
| `get_transaction_ref(session_id)` | No | Store the gateway's id for a settled payment. | `None` |
| `supported_currencies()` | No | Commera does not call it yet. | `None`: any currency. |
| `get_gateway_name()` | No | Commera does not call it yet. | The class name. |

### Status values

`get_payment_status` returns a Gateway Payment Request status. `Paid`, `Not Paid`, `Cancelled` and `Expired` change a Pending request. Any other value leaves it Pending.

The refund `status` is text from the gateway:

| Text, in any case | Gateway Refund status |
| --- | --- |
| `succeeded`, `processed` | Processed |
| `pending` | Pending |
| `failed`, `canceled`, `cancelled` | Failed |
| Empty | Processed |
| Any other text | Pending |

If `refund_payment` raises an exception, Commera marks the refund as Failed.

### Results

The models are in `bwh_payments_core.models`.

| Model | Returned by | Fields |
| --- | --- | --- |
| `CheckoutSession` | `create_session` | `session_id` and `redirect_url` are required. `success_url`, `cancel_url` and `failure_url` are optional. |
| `RefundResult` | `refund_payment`, `get_refund_status`, `list_refunds` | `refund_id`, `status` and `amount`. All are optional. |
| `WebhookEvent` | `handle_webhook` | See [Webhooks](#webhooks). |

`create_session` gets `reference`, which is the name of the Gateway Payment Request. It also gets `customer`, a dict with `ref`, `email`, `phone`, `name` and `address`. With `return_url`, send the shopper to that URL after a paid, failed or cancelled checkout.

### Class attributes

| Attribute | Use |
| --- | --- |
| `label` | The card title on Settings > Payments, the Payment Gateway Profile name and the Mode of Payment name. Do not change it after a site uses it. |
| `credential_fields` | The fieldnames that the Single must define. Commera does not read it at run time. A test uses it to check the Single. |
| `description` | One line under the card title. |
| `docs_url` | A link to the place where a merchant finds the credentials. |
| `logo` | An image URL for the card, such as `/assets/my_app/images/tamara.svg`. |

Commera does not read `logo_dark`, `logo_file`, `logo_dark_file` or `reusable_checkout` yet.

## Settings Single

The Single stores the credentials, and the connector reads them from `self`. Put `Document` first in the class bases:

```python
from frappe.model.document import Document

from my_app.connectors.tamara.gateway import TamaraGateway


class TamaraGatewaySettings(Document, TamaraGateway):
	pass
```

Read a Password field with `self.get_password("api_key")`. Read other fields as attributes.

The Single must define each name in `credential_fields`. The command writes three fields: `enabled`, `api_key` and `webhook_secret`. Change them to match the connector. Then change `credential_fields`.

Settings > Payments builds the card from the Single:

- Each editable field shows on the card, except `enabled`, which is the card's toggle.
- Each Section Break starts a new group of fields.
- A required field must have a value before a merchant can turn on the gateway.
- A Password field shows only whether it has a value.

When a merchant turns on the gateway, Commera creates a Payment Gateway Profile and a Mode of Payment with the connector's `label` as the name.

## Register a gateway

Add the Single to `hooks.py` in your app. The command does this for you:

```python
required_apps = ["commera"]
commera_api_version = [1]
commera_hooks = {"payment_connectors": ["Tamara Gateway Settings"]}
```

Only registered gateways show on Settings > Payments. Commera does not find a gateway from its DocType name.

## Webhooks

Set the gateway to post to this URL, which the card shows:

```text
/api/method/commera.payment_gateways.api.handle_webhook?gateway=<Profile name>
```

`handle_webhook` must verify the signature first. It raises an exception to refuse a delivery. It returns `None` to ignore a delivery, or a `WebhookEvent`:

| Field | Use |
| --- | --- |
| `session_id` | The session of a payment event. |
| `status` | The new status. Required. |
| `event_id` | The gateway's id for the event. Commera uses it to ignore a repeated delivery. |
| `sync_status` | When true, Commera calls `get_payment_status` and does not use `status`. Use it when a payment needs a capture, so that the capture does not run in a guest request. |
| `refund_id` | The refund of a refund event. An event needs this field or `session_id`. |
| `refund_amount` | The amount in major units. Commera needs it for a refund that was raised outside Commera. |
| `transaction_ref` | The id of the settled payment. Commera uses it to find the payment request of a refund that was raised outside Commera. |

| What happens | Answer to the gateway | Result in Commera |
| --- | --- | --- |
| The profile is missing or off | 400 | Nothing is logged. |
| The verification fails | 400 | A failed Integration Request and an Error Log are logged. The gateway can send the event again. |
| `handle_webhook` returns `None` | 200 | A completed Integration Request is logged. No payment changes. |
| No payment request matches the event | 200 | A failed Integration Request is logged. |
| The event matches a payment request | 200 | A background job applies the event. |
| The job fails | 200, already sent | The Integration Request is Failed. Retry it with `commera.payment_gateways.api.retry_webhook`. |

To make the job try again when the gateway has an outage, raise `bwh_payments_core.connectors.GatewayUnavailableError` from the connector.

## Checks and failures

| When | What Commera checks | Result of a problem |
| --- | --- | --- |
| `bench migrate` and app install | Each registered DocType exists, is a Single and subclasses `PaymentGatewayBase`. | The command stops with the problem. |
| `bench migrate` and app install | A Single with a name that ends in ` Gateway Settings` implements the contract but is not registered. | Commera prints a warning. |
| Profile save | The Single implements the contract. | The save is refused. |
| Hourly job | Each request that has been Pending for 10 minutes to 6 hours. | `get_payment_status` runs again, so a missed webhook does not leave the request Pending. |

An app that declares a different `commera_api_version` does not show on Settings > Payments.

Commera does not turn off a Payment Gateway Profile when its app is uninstalled. Turn off the gateway first.

## Tests

Tests must not call a live gateway. Each connector returns its stub client from `get_client` when `frappe.in_test` is true:

```python
def get_client(self) -> BaseTamaraClient:
	if frappe.in_test:
		return StubTamaraClient()

	return LiveTamaraClient(self.get_password("api_key"))
```

### Connector tests

The command writes a test with six cases. It covers the stub guard, minor units, status, refunds, and signed and forged webhooks. In an app, run it with this command:

```bash
bench --site <site> run-tests --module my_app.connectors.tamara.test_tamara
```

The stub client has these helpers:

- `reset()` clears the stub. Call it in `setUp`.
- `pay(payment_id)` marks a payment as paid.
- `created_payments` and `created_refunds` hold each request that the stub got.

`stub.py` also has `build_payment_event` and `sign_payload`, which make a signed webhook.

Stubs for the four connectors are in `bwh_payments_core.connectors.<gateway>.stub`, such as `StubStripeClient`.

To check a Single against its connector:

```python
missing = [
	field
	for field in get_controller(doctype).credential_fields
	if not frappe.get_meta(doctype).has_field(field)
]
```

### Payment flow tests

`bwh_payments_core.testing` runs the real payment request, refund and webhook code on an in-memory gateway. It needs a site with Commera, and it uses the Razorpay Gateway Settings Single.

```python
import frappe
from bwh_payments_core import testing
from frappe.tests import IntegrationTestCase


class TestPayment(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.reference = frappe.get_doc({"doctype": "ToDo", "description": "Payment test"}).insert()
		cls.gateway = testing.configure_test_gateway()

	def setUp(self):
		testing.reset()

	def test_a_payment_settles_the_request(self):
		payment_request = frappe.get_doc(
			{
				"doctype": "Gateway Payment Request",
				"gateway": self.gateway,
				"amount": 1000,
				"currency_code": "INR",
				"ref_doctype": "ToDo",
				"ref_docname": self.reference.name,
			}
		).insert(ignore_permissions=True)

		testing.pay(payment_request.name)

		payment_request.reload()
		self.assertEqual(payment_request.status, "Paid")
```

| Helper | Use |
| --- | --- |
| `configure_test_gateway(name)` | Make an enabled profile on the in-memory gateway. |
| `remove_test_gateway(name)` | Delete the profile and its requests. |
| `reset()` | Clear the in-memory gateway. Call it in `setUp`. |
| `pay(payment_request)` | Pay the request and sync its status. |
| `set_next_refund_status(status)` | Set the answer to the next refund: `Pending`, `Processed` or `Failed`. |
| `set_refund_status(refund, status)` | Set the status that `sync_refunds` reads. |
| `send_refund_webhook(refund, status)` | Post a signed event for a refund. |
| `send_external_refund_webhook(payment_request, amount, status)` | Post a signed event for a refund that was raised outside Commera. |
| `without_commits()` | Turn commits off inside a block. |

Refunds and webhook logs commit, so the test rollback does not remove them. Wrap the test class in `without_commits()`, or call `remove_test_gateway()` after the class rollback.

## Upgrade from bwh_payments

A site that runs `bwh_payments` keeps its gateways, credentials, payments and refunds. No rows move.

1. Update Commera. If you do not use `bench update`, run `bench setup requirements` to install the library.
2. Run `bench --site <site> migrate` on each site.
3. After every site has migrated, run `bench remove-app bwh_payments`.

The migrate does these steps:

1. It moves the DocTypes from the "BWH Payments" module to the "Payment Gateways" module.
2. It takes `bwh_payments` off Installed Apps. It does not run an uninstall, so no data goes.
3. It creates Gateway Refund rows from each request's refunded total. If the logs do not explain the total, it creates one row for the total.

Webhooks that post to `bwh_payments.bwh_payments.webhook.handle` keep working. Commera sends them to its own endpoint, so you do not have to change the gateway dashboards.

Do not install `bwh_payments` on a Commera site again. Both apps define the same DocTypes.
