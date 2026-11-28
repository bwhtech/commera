# Commera e2e

Browser tests for Commera's money paths, written with `@playwright/test`. They run against a
store that `commera.tests.e2e_support.seed` builds from an empty site.

This is its own npm package, so Playwright never enters `dashboard/package-lock.json`.

| Project | Folder | What it covers |
|---|---|---|
| `smoke` | `smoke/` | Every `/commera` route renders, with no console error and no HTTP response of 400 or more. |
| `journeys` | `journeys/` | Shopper and merchant flows end to end, each in its own browser context. |
| `screens` | `screens/` | Single screens that are not part of a journey (theme editor, navigation, state flows). |

## Run it against a devbox

Run Playwright on the box, next to the bench. The bench helper calls `bench`, so it has to be on
the same machine.

```bash
cd ~/frappe-bench
bench new-site e2e.localhost --admin-password admin --install-app erpnext
bench --site e2e.localhost install-app commera
bench --site e2e.localhost migrate
bench --site e2e.localhost set-config allow_tests 1
bench --site e2e.localhost execute commera.tests.e2e_support.seed   # safe to re-run

# Node does not resolve *.localhost the way Chrome does.
echo "127.0.0.1 e2e.localhost" | sudo tee -a /etc/hosts

# If default_site is set, port 8000 serves that site for every host name, so give the new site its own port.
bench --site e2e.localhost serve --port 8001 &

cd apps/commera/e2e
npm ci
npx playwright install chromium
COMMERA_BASE=http://e2e.localhost:8001 npx playwright test --project smoke
npx playwright show-report
```

Never point the suite at `commera-demo.localhost`. Journeys change gateway and store settings.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `COMMERA_BASE` | `http://e2e.localhost:8000` | Site URL |
| `COMMERA_FRESH_BASE` | unset | A second site where setup never ran, for fresh-site onboarding |
| `COMMERA_SITE` | host name of `COMMERA_BASE` | Site name passed to `bench --site` |
| `COMMERA_BENCH` | `~/frappe-bench` | Bench directory for the bench helper |
| `COMMERA_ADMIN_PASSWORD` | `admin` | Administrator's password |
| `COMMERA_MERCHANT_EMAIL` / `COMMERA_MERCHANT_PASSWORD` | `merchant@e2e.commera.test` / `admin` | The Commera Admin user that the seed creates. Set the same values for the seed. |
| `COMMERA_RUN_ID` | random | Run id used in data names |

## Seed

`seed()` runs `commera.install.before_tests`, then the Summer demo without its analytics step.
Then it adds an outgoing Email Account with no real SMTP (emails only queue), turns on guest
checkout and COD, marks onboarding as done, and creates the merchant user. Each helper in
`commera/tests/e2e_support.py` refuses to run unless `allow_tests` is set in the site config.

## lib/

- `auth.setup.ts` signs in Administrator and the merchant once and saves the sessions in `.auth/`.
  `newContext(browser, 'admin' | 'merchant' | 'guest')` opens one context per actor.
- `api.ts`: `Api.for(context)` calls `/api/method/...` with that context's cookies and CSRF token,
  so the call has the same permissions as the signed-in user.
- `bench.ts`: helpers for steps that have no HTTP route. They run
  `bench --site <site> execute commera.tests.e2e_support.<fn>`:
  `getSignupCode(email, purpose?)` reads the signup OTP from Redis, and `markPaymentPaid(reference)`
  sets a checkout's Gateway Payment Request to Paid, which places the order.
- `fixtures.ts`: `test` with a `problems` fixture (console errors, page errors, failed requests,
  HTTP responses of 400 or more). `realProblems()` filters out the known defects in `KNOWN_PROBLEMS`.
- `data.ts`: run-scoped names and cleanup.

## Data contract

- Name every row a spec writes `E2E-<runid>-…` with `e2eName(label)`.
- Register its removal with `useCleanup()` in the same `describe`. Cleanups run in `afterAll`, in
  reverse order, and one that fails does not stop the others.
- Archive products (`disabled: 1`); never delete them. Before you delete a collection, move its
  items to another collection. Disable shopper users; never delete them, because deleting a User
  also deletes its Contact and Customer.
- If a run is killed mid-flight, its rows stay under the `E2E-` prefix. Find them by that prefix
  and remove them by hand.

## CI

The `e2e` job in `.github/workflows/ci.yml` runs on pull requests and every Monday at 03:00 UTC
on develop. It seeds `test_site`, starts the web server, a worker and socketio, then runs all
projects. If the job fails, download the `playwright-report` artifact and open a trace with
`npx playwright show-trace`.
