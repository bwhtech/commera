# Commera Builder plugin

The Commera theme bar for the Frappe Builder editor. Commera ships it through Builder's `builder_plugins` hook, so a site with Commera and Builder lists it in the editor's Plugins panel. A System Manager enables it there once.

`bench build --app commera` builds it into `commera/public/builder_plugins/builder_plugin`, which `/assets` serves. To build only the plugin, run `yarn build:builder_plugin` in the app root.

- `manifest.json`: the plugin's name, label and version. Raise `version` when the plugin changes.
- `src/main.js`: registers the toolbar item. Builder supplies `builder`, `vue`, `pinia` and `frappe-ui`, so the build leaves them out.
- `DESCRIPTION.md`: what the Plugins panel shows to users.

The panel calls `commera.api.admin.builder_theme`.
