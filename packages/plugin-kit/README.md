# @commera/plugin-kit

The Vite config every Commera plugin uses to build what it adds to the Commera dashboard.

## Set up a plugin

```
my_app/                              # app root
├── package.json
├── yarn.lock                        # commit it: bench runs `yarn install --frozen-lockfile`
├── commera/
│   ├── vite.config.js
│   ├── pages/jobs/index.vue         # a page, with a sidebar row
│   ├── order/cards/status/index.vue # a card on the order page
│   ├── order/actions/resend/index.vue
│   ├── settings/index.vue           # the app's Settings tab
│   ├── plugin-icon.svg              # optional app logo
│   └── shared/                      # anything else is your own code
└── my_app/public/commera/           # build output, gitignored
```

```json
{
	"scripts": {
		"build": "vite build --config commera/vite.config.js"
	},
	"devDependencies": {
		"@commera/plugin-kit": "link:../commera/packages/plugin-kit",
		"@vitejs/plugin-vue": "^5.2.1",
		"vite": "^5.4.11",
		"vue": "^3.5.15"
	}
}
```

```js
// commera/vite.config.js
import { defineConfig } from 'vite';
import commera from '@commera/plugin-kit/vite';

export default defineConfig({ plugins: [commera()] });
```

Keep `vue` on the same minor version as the Commera dashboard. The app compiles its templates with its own
`vue`, but they run on the dashboard's copy.

## Add a placement

Run `bench commera add <kind> <name>` inside your app's folder to add one placement with a starter that builds:

| Kind | Writes |
| --- | --- |
| `page` | `commera/pages/<name>/index.vue`; with `--detail`, also `[...id].vue`, one record's view, which the list opens with `navigate('<name>/<id>')` |
| `order-card`, `product-card`, `customer-card` | `commera/<record>/cards/<name>/index.vue` |
| `order-action`, `product-action`, `customer-action` | `commera/<record>/actions/<name>/index.vue` and a whitelisted `<name>_<record>(name)` in your `api.py` |
| `settings` | `commera/settings/index.vue` (no name: one per plugin) |
| `command` | `commera/commands/<name>/index.vue` and a whitelisted `<name>()` in your `api.py` |

The command never overwrites: it stops when the placement or the method already exists.

## Placements

The folder decides where a plugin goes. `places.json` is the one list; Commera's server reads it too.
`<name>` is 1 to 40 lowercase letters, digits and hyphens, and is also the URL slug.

| Path under `commera/` | Where it shows | `plugin` fields: **required** / optional |
| --- | --- | --- |
| `pages/<name>/index.vue` | `/commera/plugins/<app>/<name>`, plus a sidebar row | **label** / icon, requires, condition, sidebar, order |
| `{order,product,customer}/cards/<name>/index.vue` | A card on that record's page | **label** / requires, condition, order |
| `{order,product,customer}/actions/<name>/index.vue` | A row in that page's More actions menu | **label** / icon, requires, condition, method, confirm, order |
| `settings/index.vue` | The app's tab in Settings | **label** / icon, requires, condition, doctype |
| `commands/<name>/index.vue` | A row in the search palette's Plugins group (Cmd+K), while the user types | **label, method** / icon, keywords, requires, condition, confirm, order |

Each placement's `index.vue` starts with a plain `<script>` that holds one literal:

```vue
<script>
export const plugin = {
	label: 'Print status',
	condition: 'my_app.commera_conditions.has_print_jobs',
};
</script>

<script setup>
// the card's own code
</script>
```

- An action has a template (Commera opens it in a dialog) or a whitelisted `method` (Commera runs it,
  after `confirm` if given). Never both.
- Commera calls an action's `method` as `method(name=<record name>)`, so the parameter must be called `name`,
  whatever the record is: `def send_order(name)`, not `def send_order(sales_order)`. If it returns a string,
  Commera shows that string in the success toast. Any other return value shows "<label> done". Raise with
  `frappe.throw` to show an error.
- A command has no template and no `<script setup>`: the plain `<script>` is the whole file. Commera calls
  its `method()` with no arguments, after `confirm` if given, and toasts the returned string or "<label> done".
  `keywords` is a list of extra words to match, such as `['qikink', 'print']`; the app's title always matches.
- Your pages appear in the palette's Go to group automatically; there is nothing to declare.
- A settings tab has a template, or `doctype`: a Single that Commera renders as self-saving rows. Never both.
- `condition` and `method` are dotted paths that start with your app's module name. A page or settings
  `condition` takes no arguments; a card or action `condition` gets `(doctype, name)`. A command `condition`
  takes no arguments, like a page's.
- `icon` is optional; without it the entry uses the app's icon (`commera/plugin-icon.svg`). It is a name from
  `commera/sdk/plugin_icons.json`.

Every other folder and file under `commera/` is yours: components, composables, sub-pages. Only an
`index.vue` at a placement path is built as a plugin.

### Detail pages

Put a `[...id].vue` next to a page's `index.vue` to give it a detail view:

```
pages/orders/index.vue     /commera/plugins/<app>/orders
pages/orders/[...id].vue   /commera/plugins/<app>/orders/SAL-ORD-0001
```

Everything after the page name reaches the detail as one prop named after the file, slashes included, so
`orders/INV/2026/001` gives `id = 'INV/2026/001'`. Declare it with `defineProps({ id: String })`. The detail
has no `plugin` block: it shares the page's sidebar row, `requires` and `condition`. Open it with
`navigate(\`orders/${name}\`)` and set its header with `usePage()`. A page holds one `[...name].vue`;
`[id].vue` (one URL segment) is reserved and is not built.

## App logo

Put an optional `commera/plugin-icon.svg` next to `pages/`. `bench commera init` writes a placeholder there:
the Commera logo in violet, orange, blue or green, picked once at random. It is the icon of everything your app adds, from the sidebar and Settings → Plugins
to your settings tab, palette rows and More actions rows. An entry with its own `icon` shows that one instead,
and an app with only one page shows that page's `icon` in the sidebar when it has one.

The logo shows as it is, in its own colours, so pick one that reads on both a light and a dark sidebar. A
`currentColor` in the file draws black. Without a logo, the sidebar row uses the first page's `icon`, and an
entry without an `icon` uses the dashboard's generic one.

## plugin.config.ts

Folders hold everything that draws UI. Contributions that draw nothing of their own go in one file,
`commera/plugin.config.ts` (or `.js`). Today that is sidebar actions: rows after the plugin's pages in its sidebar
group that run a function on click instead of opening a page.

```ts
import { definePlugin } from '@commera/plugin-kit'

export default definePlugin({
  sidebar: [
    { name: 'settings', label: 'Settings', icon: 'settings', order: 9, run: ({ openSettings }) => openSettings() },
    { name: 'help', label: 'Help', icon: 'circle-help', run: ({ openUrl }) => openUrl('https://example.com/help') },
  ],
})
```

The build reads `name` (1 to 40 lowercase letters, digits and hyphens, the entry's stable key), `label` (required),
`icon`, `order`, `requires` and `condition` into the manifest, with the same checks as a folder entry, and ships
the file as one module, `plugin.config.js`. `run` gets a context with `openSettings(tab)`, `navigate(to)`,
`openUrl(url)` and `toast`. The file may import only `definePlugin` from `@commera/plugin-kit`; put work that takes
time in a whitelisted method and reach it from a page.

## The dashboard draws the frame

The plugin fills the content; Commera draws the chrome around it, so every plugin looks like the rest of the
dashboard. Import these from `@commera/admin`:

| In | Use | To |
| --- | --- | --- |
| a page | `usePage()` | `setTitle(text)`, `setBreadcrumbs([{ label, to }])`, `setActions([{ label, icon, variant, onClick, loading, disabled }])`. Each takes a value, a ref or a getter. The first action is the main one; past two, the rest fold into a More menu. |
| a card | `useCard()` | `hide()`, `show()`, `setHidden(bool)`. The frame only appears after the card's first render, so hiding during setup never shows an empty card. |
| an action | `useAction()` | `setPrimary({ label, disabled, loading })`, `onSubmit(async () => …)`, `close(result)`. Resolve to close; resolve `{ reload: true }` to reload the record; throw to keep the dialog open with the error under the form. |
| all | `usePlugin()` | `plugin`, `path`, `query`, `record` (`{ doctype, name }` on cards and actions), `reload()`, `navigate(to)`, `openSettings(tab)`, `toast`, `__`. `openSettings()` opens the plugin's own Settings tab; `openSettings('payments')` opens a Commera tab. |

`navigate(to)` and a breadcrumb's `to` resolve like a link against `/commera/plugins/<app>/`: `'jobs/JOB-1'`,
`'../'` and `'/orders/SO-1'` all work the same from a page, a card or an action.

Fetch data with `useMethodRead` and `useMethodAction` from `@commera/admin`, pointed at a whitelisted
method in your app's `api.py`. Inside an action dialog, `useMethodAction` does not toast its own error.
Throw `request.error` from `onSubmit` and the dialog shows it once.

## What the build does

- Writes `my_app/public/commera/manifest.json`: `api_version`, `kit_version`, `app`, and one entry per
  plugin with its `place`, `name`, `module` (or `null` for a declarative action or settings tab), a
  content `hash`, and the `plugin` fields. Commera reads only this file to place plugins.
- Builds each placement with a template to `my_app/public/commera/<place>/<name>.js` (`settings.js` for
  the settings tab). Shared code goes to `chunks/`.
- Strips the plain `<script>` from the shipped JS, so dotted paths only live in the manifest.
- Copies `commera/plugin-icon.svg`, if there is one, to `my_app/public/commera/plugin-icon.svg` and adds `"icon": "plugin-icon.svg"`
  to the manifest.
- Does not bundle `vue`, `frappe-ui`, `frappe-ui/list`, `frappe-ui/charts` or `@commera/admin`. The dashboard
  supplies them at runtime through its import map.
- Puts `/* commera-plugin-api: 1 */` on line 1 of each module. Commera refuses a module or a manifest
  with a different version and shows the reason in place of the plugin.

## What fails the build

Folder and `plugin` problems are collected and reported together.

| Check | Example |
| --- | --- |
| An `index.vue` that declares `plugin` outside a placement | `ordr/cards/status/index.vue` |
| A placement `index.vue` without an `plugin` block | `pages/jobs/index.vue` with only a template |
| A `<name>` that is not a slug | `pages/Print_Jobs/` |
| A non-literal value | `label: t('Jobs')`, `...base`, `[key]: 1` |
| Any other statement in the plain `<script>` | `import x from './x'` |
| An unknown, missing or mistyped field | `sidebr: false` (with a did-you-mean), no `label`, `sidebar` on a card |
| An action or settings tab with both or neither of template and `method`/`doctype` | |
| A command with a template or `<script setup>` | `commands/sync/index.vue` with a `<template>` |
| A sidebar action in a folder instead of `plugin.config.ts` | `sidebar/settings/index.vue` |
| A `plugin.config.ts` item without `name`, `label` or `run`, or that imports anything but `@commera/plugin-kit` | `import { toast } from 'frappe-ui'` |
| An icon not in the list | `icon: 'printr'` |
| A dotted path outside the app | `condition: 'frappe.client.get_list'` |
| Drawing a frame the dashboard owns | importing `AppPageHeader`, `PageBody` or `PluginCard` |
| A frappe-ui resource that calls Frappe's v1 API | importing `createResource`, `createListResource`, `createDocumentResource`, `useCall`, `useList`, `useDoc`, `useDoctype`, `useNewDoc`, `frappeRequest` or `call` from `frappe-ui` |
| A `plugin-icon.svg` that is not a plain SVG | over 20 kB, not an `<svg>`, a `<script>`, an `on*` attribute, or an `href` that is not `#id` |
| A `<style>` block or a stylesheet import | `<style>.x { color: red }</style>` |
| A name the dashboard's shared modules do not export | `import { Foo } from 'frappe-ui'` |
| A subpath that is not shared | `import { TextEditor } from 'frappe-ui/editor'` |

An `index.vue` under a reserved folder (`orders/actions`, `orders/selection`, `products/actions`,
`products/selection`, `customers/actions`) only warns: those placements come in a later Commera.

Any frappe-ui or Tailwind class works. The plugin ships no CSS: the dashboard's Tailwind reads every installed
plugin's `commera/` folder, so plugin classes join its one stylesheet in Tailwind's order. `yarn dev` in the
dashboard adds a new class on save. In production a new class is styled after `bench build --app commera` or
`bench build`; a plugin-only build warns which classes are waiting for it.

The class, export and icon checks read `commera/public/plugin-host/`, which the Commera dashboard build
writes. If that folder is missing, the build warns and skips them; if it is from an older Commera, a missing
`@commera/admin` name says so. Build Commera first, or pass `commera({ hostDir })` to read another folder.

## Develop

Run `yarn dev` in `apps/commera/dashboard` and open `/commera` on its port (`<site>:8080`). Developer mode must be
on. The dev server loads every installed plugin app's `commera/` folder from source, so a saved `.vue` file updates
in place, without a reload. Each save also runs the app's `yarn build` in the background: a failed check shows
in the error overlay, and a new placement or a changed `plugin` field reloads the page. When an installed app gets
a `commera/` folder, for example from `bench commera init`, the dev server restarts itself to load it.

Your app has no `yarn dev` of its own. `bench build --app commera` builds every installed plugin after the
dashboard. In production, run `bench build --app my_app`, or `bench clear-cache` after
a `yarn build`, so the manifest is re-read.

Run the kit's own tests with `node --test test/*.test.js` (they build with the dashboard's `node_modules`).
