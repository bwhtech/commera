# Add a payment gateway

This guide shows how to add a new payment gateway, step by step. The example gateway is **Tamara**. Change the name to your gateway's name.

There are two ways to add a gateway. Pick one:

| Way | Pick it when | Where the code goes |
| --- | --- | --- |
| [A. Add it to Commera](#a-add-the-gateway-to-commera) | Every Commera shop must get the gateway. | The connector goes in the `bwh_payments_core` library. The settings page goes in Commera. You raise two pull requests. |
| [B. Add it in your own app](#b-add-the-gateway-in-your-own-app) | Only your shops need the gateway. | All the code goes in your own Frappe app. You do not change Commera. |

For the full list of methods, fields and checks, see the [payment gateway reference](payment-gateways.md).

## Words in this guide

- **Connector**: the Python class that talks to the gateway's API. It opens a checkout, reads the payment status, sends refunds and checks webhooks.
- **Settings page**: a Single DocType, such as `Tamara Gateway Settings`. It stores the gateway's keys. Its class uses the connector.
- **Registry**: the `payment_connectors` list in `hooks.py`. Commera shows a card on **Settings > Payments** for each gateway in this list.

## Before you start

- You have a bench with Commera installed on a site.
- `developer_mode` is on for the site, so that Frappe writes DocType files to disk:

  ```bash
  bench --site <site> set-config developer_mode 1
  ```

- You have the gateway's API documentation and a test (sandbox) account.

## A. Add the gateway to Commera

### Part 1: add the connector to the library

The connector code lives in the `bwh_payments_core` library: https://github.com/bwhtech/bwh_payments_core

1. Clone the library into your bench folder, and make a branch:

   ```bash
   cd ~/frappe-bench
   git clone https://github.com/bwhtech/bwh_payments_core
   cd bwh_payments_core
   git checkout -b feat/tamara
   ```

   If you cannot push to `bwhtech/bwh_payments_core`, fork it on GitHub first and clone your fork.

2. Run the scaffold command inside the library folder:

   ```bash
   bench commera payment-gateway new Tamara
   ```

   The command knows that it is in the library. It writes only the connector and its test:

   ```text
   bwh_payments_core/connectors/tamara/gateway.py   the connector class, TamaraGateway
   bwh_payments_core/connectors/tamara/base.py      the API client interface and the response models
   bwh_payments_core/connectors/tamara/live.py      the client that calls the real API
   bwh_payments_core/connectors/tamara/stub.py      a fake client for tests
   tests/test_tamara.py                             six tests for the connector
   ```

   The name can have letters, digits and spaces. You cannot use the name of a gateway that Commera already has (Razorpay, Stripe, Telr, Tabby).

3. Change `live.py` to call the gateway's real API. Set `BASE_URL`, the endpoints and the request fields. The file starts with a placeholder URL, `https://api.example.com`.

4. Change `gateway.py`:
   - Set `description` to one short line, such as `"Buy now, pay later. Saudi Arabia and UAE."`.
   - Set `docs_url` to the page where a shop owner finds the API keys. It must start with `https://`.
   - Set `credential_fields` to the name of every settings field that the connector reads, such as `("api_key", "webhook_secret", "currency")`. A test reads the code and fails if a field is missing from this list, or if the list has a field that the code does not read.
   - Change `STATUS_MAP` and `handle_webhook` to match the gateway's statuses and webhook signature. Read the webhook body with `frappe.parse_json(payload.decode())`, not `json.loads`.

5. Add the new connector to the shared tests. Open `tests/test_connectors.py`, import the two classes, and add one line to `GATEWAYS`:

   ```python
   from bwh_payments_core.connectors.tamara.gateway import TamaraGateway
   from bwh_payments_core.connectors.tamara.stub import StubTamaraClient

   GATEWAYS = {
   	...
   	TamaraGateway: StubTamaraClient,
   }
   ```

6. Run the tests in a virtual environment. They do not need a bench or a site. The library needs Python 3.14:

   ```bash
   python3.14 -m venv .venv
   . .venv/bin/activate
   pip install -e ".[test]" pre-commit
   python -m pytest
   ```

7. Run the linters, the same as CI:

   ```bash
   pre-commit run --all-files
   ```

   If a hook says that it changed files (for example, it sorted imports), run the command again until every hook passes.

8. Commit, push and open a pull request to `main` of `bwhtech/bwh_payments_core`. If git asks who you are, set `git config user.name` and `git config user.email` in this clone first.

   ```bash
   git add bwh_payments_core/connectors/tamara tests/test_tamara.py tests/test_connectors.py
   git commit -m "feat(tamara): add the tamara connector"
   git push -u origin feat/tamara
   ```

   In the pull request, say which gateway account you tested with, and paste the test output.

9. After the pull request merges, a maintainer publishes a GitHub release, such as `v0.1.2`. The release uploads the library to PyPI. Commera can use the connector only after this version is on PyPI.

### Part 2: add the settings page to Commera

1. In `apps/commera`, make a branch from `develop`:

   ```bash
   cd ~/frappe-bench/apps/commera
   git checkout develop
   git pull
   git checkout -b feat/tamara-gateway
   ```

2. Install the library with your connector.
   - **Before the library release exists** (the usual case while you work), install your clone:

     ```bash
     cd ~/frappe-bench
     ./env/bin/pip install -e ./bwh_payments_core
     ```

   - **After the release is on PyPI**, point Commera at it. In `pyproject.toml`, change the versions in this line, then run `bench setup requirements`:

     ```toml
     "bwh-payments-core>=0.1.2,<0.2",
     ```

   The pull request must have the `pyproject.toml` change before it merges.

3. Make the settings page. In Desk, go to **DocType > New** and fill in:
   - **Name**: `Tamara Gateway Settings`
   - **Module**: `Payment Gateways`
   - **Is Single**: on
   - **Fields**: one `Check` field named `enabled`, and one field for each name in `credential_fields`. Use the `Password` type for secret keys.

   Save it. Frappe writes the files to `commera/payment_gateways/doctype/tamara_gateway_settings/`.

4. Make the settings page use the connector. Open `tamara_gateway_settings.py` and change the class so that `Document` comes first:

   ```python
   from bwh_payments_core.connectors.tamara.gateway import TamaraGateway
   from frappe.model.document import Document


   class TamaraGatewaySettings(Document, TamaraGateway):
   	pass
   ```

   `razorpay_gateway_settings.py` in the same folder is a working example.

5. Add the settings page to the registry. In `commera/hooks.py`, add one line to `payment_connectors`:

   ```python
   "payment_connectors": [
   	"Razorpay Gateway Settings",
   	"Stripe Gateway Settings",
   	"Telr Gateway Settings",
   	"Tabby Gateway Settings",
   	"Tamara Gateway Settings",
   ],
   ```

6. Add the settings page to Commera's tests. In `commera/payment_gateways/tests/test_connectors.py`, add `"Tamara Gateway Settings"` to `GATEWAY_SETTINGS`.

7. Migrate, restart, and run the tests:

   ```bash
   bench --site <site> migrate
   bench restart
   bench --site <site> set-config allow_tests true
   bench --site <site> run-tests --module commera.payment_gateways.tests.test_connectors
   ```

   `bench restart` loads the new code into the web server and the workers. If you run the bench with `bench start`, stop it and start it again instead. The output must end with `Ran 4 tests` and `OK`. Run this test on a site with no other gateway app, because it checks the exact list of gateways.

   If the migrate stops with an error about `payment_connectors`, the name in `hooks.py` does not match the DocType, the DocType is not a Single, or its class does not use the connector.

8. Check it in the browser. Open **Settings > Payments** in the Commera dashboard (`/commera`). A **Tamara** card shows. Fill in the test keys, turn the card on, and pay for a test order in the storefront.

9. Commit and open a pull request to `develop` of `bwhtech/commera`:

   ```bash
   git add pyproject.toml commera/hooks.py commera/payment_gateways/doctype/tamara_gateway_settings commera/payment_gateways/tests/test_connectors.py
   git commit -m "feat(payments): add the tamara gateway"
   git push -u origin feat/tamara-gateway
   ```

   In the pull request, link the library pull request, and add a screenshot of the Tamara card.

## B. Add the gateway in your own app

You do not change Commera or the library. The scaffold command makes everything in one app.

1. Run the command in the bench folder, outside any app:

   ```bash
   cd ~/frappe-bench
   bench commera payment-gateway new Tamara
   ```

   The command makes a new app named `commera_tamara`, installs it into the bench's Python, and adds it to `sites/apps.txt`. To pick another name, add `--app-name my_payments`.

   You already have an app? Run the command inside that app's folder, or add `--app my_app`. The command then adds the gateway to that app.

   The command writes these files. The paths start in the app's folder, `apps/<app>/`, which has a Python package with the same name inside it:

   ```text
   <app>/connectors/tamara/gateway.py                 the connector class, TamaraGateway
   <app>/connectors/tamara/base.py                    the API client interface and the response models
   <app>/connectors/tamara/live.py                    the client that calls the real API
   <app>/connectors/tamara/stub.py                    a fake client for tests
   <app>/connectors/tamara/test_tamara.py             six tests for the connector
   <app>/<module>/doctype/tamara_gateway_settings/    the settings page
   ```

   For example, for the app `commera_tamara` the connector is at `apps/commera_tamara/commera_tamara/connectors/tamara/gateway.py`. `<module>` is the first module in the app's `modules.txt`, written in lowercase with underscores.

   It also adds these lines to the app's `hooks.py`:

   ```python
   required_apps = ["commera"]
   commera_api_version = [1]
   commera_hooks = {"payment_connectors": ["Tamara Gateway Settings"]}
   ```

2. Change `live.py` and `gateway.py`, the same as steps 3 and 4 in [Part 1](#part-1-add-the-connector-to-the-library).

3. The settings page has three fields: `enabled`, `api_key` and `webhook_secret`. If your gateway needs other keys, change the fields in Desk (developer mode), and change `credential_fields` in `gateway.py` to match.

4. Install the app on your site, then restart the bench so that the web server and the workers load the new app:

   ```bash
   bench --site <site> install-app commera_tamara
   bench restart
   ```

   If the app is already on the site, run `bench --site <site> migrate` instead of `install-app`. If you run the bench with `bench start`, stop it and start it again instead of `bench restart`. Until you restart, every page shows an error such as `No module named 'commera_tamara'`.

5. Run the connector tests. Tests are off on a site until you turn them on:

   ```bash
   bench --site <site> set-config allow_tests true
   bench --site <site> run-tests --module commera_tamara.connectors.tamara.test_tamara
   ```

   The output must end with `Ran 6 tests` and `OK`. If it says "Testing is disabled for the site", `allow_tests` is not set.

6. Open **Settings > Payments** in the Commera dashboard. A **Tamara** card shows. Fill in the test keys, turn the card on, and pay for a test order in the storefront.

7. Push your app to your own Git repository. To use it on another bench, run `bench get-app <your repo URL>` and then `install-app`.

## After you add a gateway

- **Webhooks**: the card shows the webhook URL. Set it in the gateway's dashboard. Commera also checks Pending payments every hour, so a missed webhook does not leave an order stuck.
- **Test keys only**: tests always use the stub client. Never put live keys in a test.
- **Do not rename the gateway** after a shop uses it. Its name is also the name of the Payment Gateway Profile and the Mode of Payment.

## Problems

| What you see | What to do |
| --- | --- |
| No card for the gateway on Settings > Payments | Check that the DocType name is in `payment_connectors` in `hooks.py`, that you ran `migrate`, and that you restarted the bench. |
| Every page shows `No module named '<app>'` | Restart the bench (`bench restart`, or stop and start `bench start`). |
| `bench commera payment-gateway new` says Commera already ships the gateway | Pick another name. |
| Migrate stops with "is declared in commera_hooks['payment_connectors'] but is not a DocType" | The name in `hooks.py` has a typo, or the DocType was not saved. |
| Migrate stops with "does not subclass bwh_payments_core.contract.PaymentGatewayBase" | Change the settings page class to `class TamaraGatewaySettings(Document, TamaraGateway)`. |
| The card cannot be turned on | A required field is empty. Fill in every key on the card. |
