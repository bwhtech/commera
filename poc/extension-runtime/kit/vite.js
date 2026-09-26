// @commera/extension-kit/vite: the one build config every Commera app uses.
//
// - Every folder under the app's `commera/` directory with an index.vue is an
//   entry, written to a fixed file name (`<module>.js`) so the server can point
//   at it without reading a manifest.
// - `vue`, `frappe-ui` and `@commera/admin` stay external: the dashboard's
//   import map supplies them at runtime, so the extension carries only its own code.
// - No CSS: a <style> block fails the build, and so does any class the
//   dashboard's stylesheet does not contain (read from the host's classes.json).
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import vue from '@vitejs/plugin-vue'

export const API_VERSION = 1
const SHARED = ['vue', 'frappe-ui', '@commera/admin']

function discoverModules(sourceDir) {
  return Object.fromEntries(
    readdirSync(sourceDir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && existsSync(join(sourceDir, entry.name, 'index.vue')))
      .map((entry) => [entry.name, join(sourceDir, entry.name, 'index.vue')]),
  )
}

// Static class="..." attributes only. Bound classes are checked by review, as
// the dashboard's own style law already forbids string-built class names.
function staticClasses(source) {
  const template = source.match(/<template>([\s\S]*)<\/template>/)?.[1] ?? ''
  return [...template.matchAll(/\sclass="([^"]*)"/g)].flatMap((match) => match[1].split(/\s+/)).filter(Boolean)
}

function guard({ hostClasses, hostExports }) {
  const known = hostClasses && existsSync(hostClasses) ? new Set(JSON.parse(readFileSync(hostClasses, 'utf8'))) : null
  const shared = hostExports && existsSync(hostExports) ? JSON.parse(readFileSync(hostExports, 'utf8')) : null
  return {
    // Every name an extension imports from a shared specifier must be one the
    // dashboard's runtime entry exports; otherwise the browser would refuse the
    // module with "does not provide an export named …".
    generateBundle(_options, bundle) {
      if (!shared) return
      for (const chunk of Object.values(bundle)) {
        if (chunk.type !== 'chunk') continue
        for (const [specifier, names] of Object.entries(chunk.importedBindings)) {
          const missing = shared[specifier] ? names.filter((name) => !shared[specifier].includes(name)) : []
          if (missing.length) {
            this.error(`${chunk.fileName}: '${specifier}' does not share ${missing.join(', ')} with extensions`)
          }
        }
      }
    },
    name: 'commera-extension-guard',
    enforce: 'pre',
    resolveId(source) {
      // The import map shares the package roots only; a subpath would pull a
      // second copy of the library into the extension.
      if (SHARED.some((name) => source.startsWith(`${name}/`))) {
        this.error(`import '${source}' is not shared with extensions; import from '${source.split('/')[0]}'`)
      }
    },
    transform(code, id) {
      if (id.includes('?vue&type=style')) {
        this.error(`${id.split('?')[0]}: extensions ship no CSS in v1; use frappe-ui and dashboard classes`)
      }
      if (!known || !id.endsWith('.vue')) return
      const unknown = staticClasses(code).filter((name) => !known.has(name))
      if (unknown.length) {
        this.error(`${id}: classes the dashboard does not ship: ${[...new Set(unknown)].join(', ')}`)
      }
    },
  }
}

export default function commeraExtension({ root = process.cwd(), hostClasses, hostExports } = {}) {
  const sourceDir = resolve(root, 'commera')
  const modules = discoverModules(sourceDir)
  return [
    guard({ hostClasses, hostExports }),
    vue(),
    {
      name: 'commera-extension-build',
      config: () => ({
        root: sourceDir,
        publicDir: false,
        build: {
          outDir: resolve(root, 'dist'),
          emptyOutDir: true,
          target: 'es2022',
          minify: true,
          lib: { entry: modules, formats: ['es'], fileName: (_format, name) => `${name}.js` },
          rollupOptions: {
            external: SHARED,
            output: {
              banner: `/*! commera-extension-api: ${API_VERSION} */`,
              chunkFileNames: 'chunks/[name]-[hash].js',
            },
          },
        },
      }),
    },
  ]
}
