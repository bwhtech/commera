# Commera Builder plugin

The Commera theme bar for the Frappe Builder editor. Commera ships it through Builder's `builder_plugins` hook, so a site with Commera and Builder lists it in the editor's Plugins panel. A System Manager enables it there once.

`bench build --app commera` builds it into `commera/public/builder_plugins/builder_plugin`, which `/assets` serves. To build only the plugin, run `yarn build:builder_plugin` in the app root.

- `manifest.json`: the plugin's name, label and version. Raise `version` when the plugin changes.
- `src/main.js`: registers the toolbar item and the Store themes dashboard view (`src/dashboard/`). Builder supplies `builder`, `vue`, `pinia`, `frappe-ui`, `frappe-ui/editor` and `frappe-ui/list`, so the build leaves them out.
- The dashboard view copies the layout of Commera's Themes screen (`dashboard/src/pages/storefront/Themes.vue`). Keep the two in step.
- The editor's stylesheet loads after the plugin's, so an editor utility such as `w-28` beats a responsive `sm:w-40` of the plugin's. Use one layout, or `!` for a size the editor sets, such as a `lucideIcon()` icon's `h-[1em]`.
- `DESCRIPTION.md`: what the Plugins panel shows to users.

The panel calls `commera.api.admin.builder_theme`.
