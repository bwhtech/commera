import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import { fileURLToPath } from 'node:url'

// The bare specifiers an extension may import. Each maps to a runtime entry
// whose chunk keeps its export names, so the dashboard's own code and every
// extension resolve to the same module instances (one Vue, one frappe-ui
// toast/dialog state, one provide/inject tree).
const SHARED = {
  vue: 'runtime-vue',
  'frappe-ui': 'runtime-frappe-ui',
  '@commera/admin': 'runtime-commera-admin',
}

function sharedRuntime() {
  return {
    name: 'commera-shared-runtime',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      handler(html, ctx) {
        const imports = {}
        for (const [specifier, entryName] of Object.entries(SHARED)) {
          const chunk = Object.values(ctx.bundle).find(
            (output) => output.type === 'chunk' && output.isEntry && output.name === entryName,
          )
          if (!chunk) throw new Error(`shared runtime entry ${entryName} was not emitted`)
          imports[specifier] = `/${chunk.fileName}`
        }
        // head-prepend: an import map only applies to module scripts that come after it.
        return [
          {
            tag: 'script',
            attrs: { type: 'importmap' },
            children: JSON.stringify({ imports }, null, 2),
            injectTo: 'head-prepend',
          },
        ]
      },
    },
    // The class vocabulary extensions may use: every class selector in the
    // built stylesheet. The kit fails an extension build on anything else.
    generateBundle(_options, bundle) {
      const classes = new Set()
      for (const output of Object.values(bundle)) {
        if (output.type !== 'asset' || !output.fileName.endsWith('.css')) continue
        const css = String(output.source)
        for (const match of css.matchAll(/\.((?:\\.|[\w-])+)/g)) {
          classes.add(match[1].replace(/\\(.)/g, '$1'))
        }
      }
      // The names each shared specifier exports, so the kit can refuse an import
      // the runtime would not satisfy at build time rather than in the browser.
      const exportsBySpecifier = {}
      for (const [specifier, entryName] of Object.entries(SHARED)) {
        const chunk = Object.values(bundle).find((output) => output.type === 'chunk' && output.isEntry && output.name === entryName)
        exportsBySpecifier[specifier] = chunk.exports
      }
      this.emitFile({ type: 'asset', fileName: 'shared-exports.json', source: JSON.stringify(exportsBySpecifier, null, 2) })
      this.emitFile({
        type: 'asset',
        fileName: 'classes.json',
        source: JSON.stringify([...classes].sort()),
      })
    },
  }
}

const runtime = (file) => fileURLToPath(new URL(`./src/runtime/${file}`, import.meta.url))

export default defineConfig({
  plugins: [
    frappeui({ frappeProxy: false, jinjaBootData: false, buildConfig: false }),
    vue(),
    sharedRuntime(),
  ],
  build: {
    outDir: 'dist',
    target: 'es2022',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: fileURLToPath(new URL('./index.html', import.meta.url)),
        'runtime-vue': runtime('vue.js'),
        'runtime-frappe-ui': runtime('frappe-ui.js'),
        'runtime-commera-admin': runtime('commera-admin.js'),
      },
      // Without this Rollup may tree-shake or rename the runtime entries'
      // exports, since nothing inside the host imports them by those names.
      preserveEntrySignatures: 'exports-only',
    },
  },
})
