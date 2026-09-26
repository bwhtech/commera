# Extension runtime POC

A front-end-only proof of the runtime in [spec 2 §2](../../docs/specs/commera-apps/02-platform-implementation.md):
a frappe-ui host app that is **built once**, and extensions from **other folders, built separately**,
loaded at runtime and rendered with the host's own Vue and frappe-ui.

No Frappe here. `server.mjs` plays Frappe's part: it serves the host build, each app's build under
`/assets/<app>/commera/`, a registry standing in for `boot.extensions`, and a few mock whitelisted
methods.

```
host/        frappe-ui app (the "dashboard"). Its build exposes vue, frappe-ui and
             @commera/admin through an import map, and emits classes.json and
             shared-exports.json for the kit.
kit/         @commera/extension-kit/vite: the one build config every app uses.
apps/
  printful/  extensions.json (stands in for get_extensions())
             commera/printful-page, commera/printful-order-block
  broken/    one block that throws, to prove isolation
server.mjs   stand-in for Frappe
verify.mjs   drives the build in Chromium and checks every claim below
measure*.mjs bundle-size measurements
```

## Run

```bash
npm install
npm run build        # host once, then each app on its own
npm run verify       # 14 checks, screenshots in ./screenshots
npm run serve        # http://localhost:4173 to click around
node measure.mjs && node measure-transfer.mjs
```

Rebuild a single app (`npm run build -w apps/printful`) and reload: the change shows up with the host
untouched, because the server stamps each module URL with `?v=<mtime>`.

## What it proved

`npm run verify`, all passing:

| Claim | How it is checked |
| --- | --- |
| An app adds a sidebar link to a host built without it | Link from `apps/printful/extensions.json` renders in the host's Apps section |
| Extension modules load from the app's own folder | `/assets/printful/commera/printful-page.js` fetched at runtime |
| Extensions use the host's data helpers | `useMethodRead` (frappe-ui `useCall`) from `@commera/admin` returns mock data |
| One frappe-ui instance | A `toast()` raised in the extension renders in the host's `FrappeUIProvider` toaster (vue-sonner state is module-level) |
| Overlays work | A frappe-ui `Dialog` from the extension opens, takes input and closes |
| One Vue instance | The order block reads `resource` through `inject()` of a key the host `provide()`s — impossible across two Vue copies |
| `navigate()` / `setTitle()` | Sub-route `/apps/printful/printful/syncs`; document title set |
| Isolation | A throwing extension becomes a failure card; the host page and the other block keep rendering |
| No duplicate runtime | Per page load, `runtime-core`, `runtime-vue`, `runtime-frappe-ui`, `runtime-commera-admin` each fetched once |
| Extensions carry only their own code | Largest extension module: 3.1 kB (1.3 kB gzip) |

Build-time guards in the kit, each seen failing on purpose:

- A class the host does not ship: `classes the dashboard does not ship: space-y-6, rounded-lg`
- A frappe-ui name the host does not share: `'frappe-ui' does not share Calendar with extensions`
- A `<style>` block, or a `frappe-ui/…` subpath import

![order page](screenshots/4-order-blocks.png)

## What it costs

The shared runtime is not free: an entry that re-exports a library keeps all of it.

| Host build | Total JS (gzip) | `/` downloads (gzip) | Page with an extension (gzip) |
| --- | --- | --- | --- |
| No shared runtime (baseline) | 94.8 kB | — | — |
| `export * from 'frappe-ui'` | 246.1 kB | 171.1 kB | 246.2 kB |
| Curated frappe-ui list (16 names) | 194.3 kB | **111.0 kB** | 194.5 kB |

So the frappe-ui surface extensions may import must be a **curated list**, not `export *`
(`host/src/runtime/frappe-ui.js`). The remaining extension-page cost is frappe-ui components this toy
host does not use itself (Select, Dropdown, Tooltip…); the real dashboard already ships nearly all of
them, so its delta should be close to the 16 kB seen on `/`. Measure again against the real dashboard
in P0.

## Not covered

- The server side: registry, permissions, conditions, hooks (spec 2 §1). The registry here is a JSON file.
- Record-condition batching, declarative actions, settings tabs.
- Dev-mode reload without a rebuild.
- In a bench each app has its own `node_modules`; here one npm workspace installs everything. The
  extensions still import neither Vue nor frappe-ui at build time: both stay external.
