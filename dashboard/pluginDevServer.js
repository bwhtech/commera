import { spawn } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { searchForWorkspaceRoot } from 'vite'
import * as compiler from 'vue/compiler-sfc'
import { discoverPlugins, pageEntryCode } from '../packages/plugin-kit/vite.js'

const PREFIX = '/@commera-plugin/'
const VIRTUAL = '\0commera-plugin:'
const BENCH = fileURLToPath(new URL('../../..', import.meta.url))

function readPluginApps() {
  const appsFile = join(BENCH, 'sites', 'apps.txt')
  if (!existsSync(appsFile)) return []
  return readFileSync(appsFile, 'utf8')
    .split('\n')
    .map((app) => app.trim())
    .filter((app) => app && app !== 'commera' && existsSync(join(BENCH, 'apps', app, 'commera')))
}

function sourceDirOf(app) {
  return join(BENCH, 'apps', app, 'commera')
}

// Without the hashes, which change on every edit, so only a new placement or changed plugin field reloads the page.
function placementsOf(app) {
  const path = join(BENCH, 'apps', app, app, 'public', 'commera', 'manifest.json')
  if (!existsSync(path)) return null
  const manifest = JSON.parse(readFileSync(path, 'utf8'))
  manifest.entries = manifest.entries.map(({ hash, ...entry }) => entry)
  return JSON.stringify(manifest)
}

// `/@commera-plugin/<app>/<place>/<name>`, where a place can hold a slash (`order/cards`).
function parseKey(key) {
  const parts = key.split('/')
  return { app: parts[0], place: parts.slice(1, -1).join('/'), name: parts.at(-1) }
}

function moduleCode(key) {
  const { app, place, name } = parseKey(key)
  const { entries } = discoverPlugins(sourceDirOf(app), { app, compiler })
  const entry = entries.find((entry) => entry.place === place && entry.name === name)
  if (!entry?.entryName) throw new Error(`${app} has no ${place}/${name}/index.vue with a template`)
  return entry.detail ? pageEntryCode(entry) : `export { default } from ${JSON.stringify(entry.file)}`
}

// Each save still runs the app's own build, so the kit's checks and the manifest the server places plugins by stay current.
function buildRunner(server) {
  const running = new Map()
  const queued = new Set()
  const failed = new Set()

  function build(app) {
    if (running.has(app)) {
      queued.add(app)
      return running.get(app)
    }
    const before = placementsOf(app)
    const job = new Promise((resolve) => {
      let output = ''
      const child = spawn('yarn', ['build'], { cwd: join(BENCH, 'apps', app), env: process.env })
      child.stdout.on('data', (chunk) => (output += chunk))
      child.stderr.on('data', (chunk) => (output += chunk))
      child.on('error', (error) => resolve({ ok: false, output: error.message }))
      child.on('close', (code) => resolve({ ok: code === 0, output }))
    }).then(({ ok, output }) => {
      running.delete(app)
      if (!ok) {
        failed.add(app)
        server.config.logger.error(`[commera] ${app} plugin build failed\n${output}`)
        server.ws.send({ type: 'error', err: { message: `${app}: plugin build failed\n\n${output.trim()}`, stack: '' } })
      } else if (failed.delete(app) || placementsOf(app) !== before) {
        // Vite has no message that only clears the error overlay; a reload is the one way to take it down.
        server.ws.send({ type: 'full-reload' })
      }
      if (queued.delete(app)) return build(app)
    })
    running.set(app, job)
    return job
  }

  return build
}

export function pluginDevServer() {
  const apps = readPluginApps()
  return {
    name: 'commera-plugin-dev-server',
    apply: 'serve',
    config: () => ({
      resolve: {
        dedupe: ['vue', 'frappe-ui'],
        alias: { '@commera/admin': fileURLToPath(new URL('./src/plugin-api/index.js', import.meta.url)) },
      },
      server: { fs: { allow: [searchForWorkspaceRoot(process.cwd()), ...apps.map(sourceDirOf)] } },
    }),
    configureServer(server) {
      const build = buildRunner(server)
      const timers = new Map()
      server.watcher.add(apps.map(sourceDirOf))
      server.watcher.on('all', (_event, file) => {
        const app = apps.find((app) => file.startsWith(`${sourceDirOf(app)}/`))
        if (!app || file.includes('/node_modules/')) return
        clearTimeout(timers.get(app))
        timers.set(app, setTimeout(() => build(app), 300))
      })
      apps.reduce((previous, app) => previous.then(() => build(app)), Promise.resolve())
    },
    resolveId(source) {
      if (source.startsWith(PREFIX)) return VIRTUAL + source.slice(PREFIX.length)
    },
    load(id) {
      if (id.startsWith(VIRTUAL)) return moduleCode(id.slice(VIRTUAL.length))
    },
  }
}
