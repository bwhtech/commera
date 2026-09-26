// Stands in for Frappe: serves the host build like /commera, each app's build
// like /assets/<app>/commera/, the registry like boot.extensions, and two mock
// whitelisted methods. Nothing here is Commera code; it only lets the browser
// exercise the real build output.
import { createServer } from 'node:http'
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { extname, join, normalize } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = fileURLToPath(new URL('.', import.meta.url))
const HOST_DIST = join(ROOT, 'host/dist')
const APPS_DIR = join(ROOT, 'apps')
const PORT = Number(process.env.PORT ?? 4173)
const TYPES = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.woff2': 'font/woff2', '.svg': 'image/svg+xml' }

// get_registry(): collect every app's entries, key them, stamp module URLs with ?v=<mtime>.
function registry() {
  return readdirSync(APPS_DIR).flatMap((app) => {
    const file = join(APPS_DIR, app, 'extensions.json')
    if (!existsSync(file)) return []
    return JSON.parse(readFileSync(file, 'utf8')).map((entry) => {
      if (!entry.module) return { app, ...entry }
      const built = join(APPS_DIR, app, 'dist', `${entry.module}.js`)
      const version = existsSync(built) ? statSync(built).mtimeMs.toFixed(0) : 'missing'
      return { app, ...entry, url: `/assets/${app}/commera/${entry.module}.js?v=${version}` }
    })
  })
}

const METHODS = {
  'print2commera.api.get_order_panel': (query) => ({
    printful_order_id: 'PF-88213', status: 'inprocess', cost: 14.2, retail: 32, sales_order: query.get('sales_order'),
  }),
  'print2commera.api.get_sync_history': () => [
    { id: 'SYNC-3', started: '2026-09-26 03:00', status: 'completed' },
    { id: 'SYNC-2', started: '2026-09-25 03:00', status: 'failed' },
  ],
  'print2commera.api.start_sync': () => ({ message: 'Printful sync started' }),
}

function send(response, status, body, type = 'application/json') {
  response.writeHead(status, { 'content-type': type })
  response.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body))
}

function sendFile(response, file) {
  if (!existsSync(file) || !statSync(file).isFile()) return send(response, 404, { error: 'not found' })
  send(response, 200, readFileSync(file), TYPES[extname(file)] ?? 'application/octet-stream')
}

createServer((request, response) => {
  const url = new URL(request.url, 'http://localhost')
  const path = normalize(decodeURIComponent(url.pathname))
  if (path === '/api/extensions') return send(response, 200, registry())
  if (path.startsWith('/api/v2/method/')) {
    const method = METHODS[path.slice('/api/v2/method/'.length)]
    return method ? send(response, 200, { data: method(url.searchParams) }) : send(response, 404, { errors: [{ message: 'no such method' }] })
  }
  const appAsset = path.match(/^\/assets\/([\w-]+)\/commera\/(.+)$/)
  if (appAsset) return sendFile(response, join(APPS_DIR, appAsset[1], 'dist', appAsset[2]))
  if (path.startsWith('/assets/')) return sendFile(response, join(HOST_DIST, path))
  sendFile(response, join(HOST_DIST, 'index.html')) // SPA fallback, like the /commera route rule
}).listen(PORT, () => console.log(`POC on http://localhost:${PORT}`))
