import { copyFileSync, mkdirSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import { pluginDevServer } from './pluginDevServer.js'

// The bare specifiers an app page may import, each mapped to a runtime entry whose chunk keeps its export names,
// so the dashboard and every app share one Vue, one frappe-ui (toasts, dialogs) and one provide/inject tree.
const SHARED = {
  vue: 'runtime-vue',
  'frappe-ui': 'runtime-frappe-ui',
  'frappe-ui/list': 'runtime-frappe-ui-list',
  'frappe-ui/charts': 'runtime-frappe-ui-charts',
  '@commera/admin': 'runtime-commera-admin',
}

const fromHere = (path) => fileURLToPath(new URL(path, import.meta.url))

// Outside the emptied outDir: bench builds apps in parallel, and the plugin kit reads these while commera rebuilds.
const PLUGIN_HOST_DIR = fromHere('../commera/public/plugin-host')

function findEntryChunk(bundle, entryName) {
  const chunk = Object.values(bundle).find((output) => output.type === 'chunk' && output.isEntry && output.name === entryName)
  if (!chunk) throw new Error(`shared runtime entry ${entryName} was not emitted`)
  return chunk
}

function sharedRuntime() {
  let base
  return {
    name: 'commera-shared-runtime',
    apply: 'build',
    configResolved(config) {
      base = config.base
      if (!base.startsWith('/')) throw new Error(`the import map needs an absolute base, got '${base}'`)
    },
    transformIndexHtml: {
      order: 'post',
      handler(_html, { bundle }) {
        const imports = Object.fromEntries(
          Object.entries(SHARED).map(([specifier, entryName]) => [specifier, base + findEntryChunk(bundle, entryName).fileName]),
        )
        // Pretty-printed so commera.html never holds `}}`, which Jinja would read as a closing tag.
        return [
          { tag: 'script', attrs: { type: 'importmap' }, children: JSON.stringify({ imports }, null, 2), injectTo: 'head-prepend' },
        ]
      },
    },
    writeBundle(_options, bundle) {
      const classes = new Set()
      for (const output of Object.values(bundle)) {
        if (output.type !== 'asset' || !output.fileName.endsWith('.css')) continue
        // Declaration bodies go first, or `.5rem` and the dots inside icon data URIs read as classes.
        const selectors = String(output.source).replace(/\{[^{}]*\}/g, '{}')
        for (const match of selectors.matchAll(/\.((?:\\.|[\w-])+)/g)) {
          classes.add(match[1].replace(/\\(.)/g, '$1'))
        }
      }
      const sharedExports = Object.fromEntries(
        Object.entries(SHARED).map(([specifier, entryName]) => [specifier, findEntryChunk(bundle, entryName).exports]),
      )
      mkdirSync(PLUGIN_HOST_DIR, { recursive: true })
      writeFileSync(`${PLUGIN_HOST_DIR}/shared-exports.json`, `${JSON.stringify(sharedExports, null, 2)}\n`)
      writeFileSync(`${PLUGIN_HOST_DIR}/classes.json`, `${JSON.stringify([...classes].sort())}\n`)
      copyFileSync(fromHere('../commera/sdk/plugin_icons.json'), `${PLUGIN_HOST_DIR}/icons.json`)
    },
  }
}

export default defineConfig({
  plugins: [
    frappeui({
      frappeProxy: {
        // `port` is the VITE dev-server port, not Frappe's. The plugin proxies to
        // whatever webserver_port common_site_config says and routes by the request's
        // Host, so browse the app at <site>:8080 to hit the right site.
        port: 8080,
        source: '^/(app|login|api|assets|files|private)(/|\\?|$)',
      },
      jinjaBootData: true,
      buildConfig: {
        indexHtmlPath: '../commera/www/commera.html',
        emptyOutDir: true,
        sourcemap: true,
        outDir: '../commera/public/commera',
        target: 'es2015',
      },
    }),
    vue(),
    sharedRuntime(),
    pluginDevServer(),
  ],
  build: {
    rollupOptions: {
      input: {
        index: fromHere('./index.html'),
        'runtime-vue': fromHere('./src/runtime/vue.js'),
        'runtime-frappe-ui': fromHere('./src/runtime/frappe-ui.js'),
        'runtime-frappe-ui-list': fromHere('./src/runtime/frappe-ui-list.js'),
        'runtime-frappe-ui-charts': fromHere('./src/runtime/frappe-ui-charts.js'),
        'runtime-commera-admin': fromHere('./src/plugin-api/index.js'),
      },
      // Nothing in the dashboard imports the runtime entries by name, so without this Rollup tree-shakes their exports.
      preserveEntrySignatures: 'exports-only',
    },
  },
  optimizeDeps: {
    exclude: ['frappe-ui'],
    include: [
      'feather-icons',
      'tippy.js',
      'engine.io-client',
      'socket.io-client',
      'debug',
    ],
  },
  server: {
    allowedHosts: true,
  },
})
