# Commera dashboard end-to-end tests

Real Chrome, real HTTP, real rows. The runner is Node's built-in `node:test`; the only
extra dependency is `puppeteer`.

## Running

```bash
cd dashboard
yarn install
yarn test:e2e:smoke   # read-only, ~40s: every route renders with no console error
yarn test:e2e         # everything, including the write flows, ~2.5 min
```

Both lanes run `tests/e2e/check-build.js` first and refuse to start against a stale bundle.
Run one spec on its own with `node --test tests/e2e/catalog.spec.js`.

## Environment

| Variable | Default | Why |
| --- | --- | --- |
| `COMMERA_BASE` | `http://dev.localhost:8000` | Site under test. The public HTTPS host is currently served through a proxy with a broken TLS chain, so the local bench webserver is the default and the public URL is the override. |
| `COMMERA_USER` / `COMMERA_PASSWORD` | `Administrator` / `Admin123` | Dashboard login. |
| `COMMERA_SITE` / `BENCH_PATH` | `dev.localhost` / `/home/frappe/frappe-bench` | Only `checkout.spec.js` uses these — see the OTP note below. |
| `COMMERA_RUN_ID` | random 6 characters | Overriding it makes a run's data names reproducible. |
| `COMMERA_ARTIFACTS` | `tests/e2e/.artifacts` | Failure screenshots and the cached login cookies. Gitignored. |

## Specs

| File | Covers |
| --- | --- |
| `smoke.spec.js` | All 16 routes render their own screen, no console error, no HTTP >= 400. Read-only. |
| `catalog.spec.js` | Create a collection, create an attribute, and the add-product dialog including the option x size grid. |
| `ops.spec.js` | Orders list (tabs, search) and detail, customers list and detail, inventory and pricing lists. Read-only. |
| `storefront.spec.js` | The navigation tree editor and the footer column editor, asserted after a reload. |
| `checkout.spec.js` | A new shopper signs up on the storefront, places a COD order, and finds it in `/account/orders`. |
| `discounts.spec.js` | A cart link's `?discount=` code is shown at checkout and reaches the COD order, `mode=add` keeps the cart and adds the code, a code typed into the default theme's promo box reaches the open checkout, and signing in merges the guest cart into the account's. |

Not covered, because there is nothing behind them yet: **Storefront > Theme** and
**Storefront > Pages** are mock screens with no endpoint, and **Product types** has no
backend at all. All three are in the smoke lane (they must still render) and nowhere else.

## Data-cleanup contract

Everything the suite writes is named `E2E-<runid>-...` or `E2E-<runid> ...`, and every
spec registers an `onCleanup` handler that runs before its browser closes:

- **Products** are archived (`catalog.update_product` with `disabled: 1`) — exactly what
  the UI's Archive action does. They can never be hard-deleted: the Style Attribute
  Configurator holds live links to their variants.
- **Collections** are deleted, after every `Item` and `Style Attribute Variant` filed
  under them is moved to a collection the store already used.
- **Attributes**, **navigation entries** and **footer columns** are deleted.
- **Orders** are deleted, after the purchase analytics event that links them.
- **Shopper users** are disabled, not deleted: deleting a `User` cascades into `Contact`
  and `Customer`.

If a run is killed mid-flight, its rows survive under the `E2E-` prefix and can be found
and removed by hand.

## Traps

- **Stale build.** The browser serves the last `yarn build`, never `dashboard/src`. The
  entry document is written to `commera/www/commera.html` and the hashed assets to
  `commera/public/commera/assets/`. `check-build.js` compares their mtimes against
  `dashboard/src` and fails the lane rather than let a green run mean nothing.
- **Real clicks only.** Use `clickByText` (an `ElementHandle.click()`, a real mouse event).
  An in-page `el.click()` does not fire the pointer events frappe-ui's Select, Autocomplete
  and Dropdown listen for, so the widget never opens.
- **The public HTTPS endpoint is broken** at the host proxy (TLS). Test against
  `COMMERA_BASE=http://dev.localhost:8000` unless that has been fixed.
- **Assert persisted state, not toasts.** A toast proves the client tried. Every write
  spec reloads and re-reads through the admin API over the same logged-in session.
- **The apply-code rate limit** counts every rate-limited storefront call per IP, so a few
  `discounts.spec.js` runs from one IP get a 429. Clear it on the site first:
  `frappe.cache.delete_keys("rl:")` in `bench --site <site> console`.
- **The promo-box test switches the store theme** to Shop Default Theme (Summer has no box)
  and switches it back in cleanup. A killed run leaves the store on the default theme.
- **The signup OTP** lives only in Redis, so `checkout.spec.js` shells out to
  `bench --site <site> console` to read it. It is the one place the suite does not go
  through HTTP, because there is no HTTP route to a one-time code.
