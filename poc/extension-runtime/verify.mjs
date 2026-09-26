// Drives the built POC in Chromium and checks the claims the specs rest on.
// Run `npm run build` first. Screenshots land in ./screenshots.
import { spawn } from 'node:child_process'
import { mkdirSync, statSync } from 'node:fs'
import { chromium } from 'playwright-core'

const PORT = 4180
const BASE = `http://localhost:${PORT}`
const CHROMIUM = process.env.CHROMIUM_PATH ?? '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
mkdirSync('screenshots', { recursive: true })

const server = spawn('node', ['server.mjs'], { env: { ...process.env, PORT: String(PORT) }, stdio: 'inherit' })
await new Promise((resolve) => setTimeout(resolve, 500))

const results = []
const check = (name, ok, detail = '') => {
  results.push({ name, ok })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`)
}

// Within one page load, each shared runtime chunk and Vue's own runtime-core
// must be fetched exactly once: a second fetch would mean a second instance.
function checkSingleRuntime(label) {
  const shared = requests.filter((path) => /\/assets\/(runtime-(vue|frappe-ui|commera-admin)|runtime-core\.esm-bundler)-/.test(path))
  check(`${label}: one copy each of Vue, frappe-ui and @commera/admin`, new Set(shared).size === shared.length && shared.length === 4, shared.join(', '))
}

const browser = await chromium.launch({ executablePath: CHROMIUM })
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })
const requests = []
page.on('request', (request) => requests.push(new URL(request.url()).pathname))
const pageErrors = []
page.on('pageerror', (error) => pageErrors.push(error.message))

try {
  // 1. The sidebar link comes from the printful app's registry entry.
  await page.goto(BASE)
  const nav = page.locator('[data-extension-nav]', { hasText: 'Printful' })
  await nav.waitFor({ timeout: 10000 })
  check('extension adds a sidebar link to a host that was built without it', await nav.isVisible())
  await page.screenshot({ path: 'screenshots/1-sidebar.png' })

  // 2. App page: separately built module, rendered with the host's Vue + frappe-ui.
  await nav.click()
  await page.locator('[data-printful-page]').waitFor({ timeout: 10000 })
  check('app page module loads from /assets/printful/commera/', requests.some((path) => path === '/assets/printful/commera/printful-page.js'))
  await page.getByText('2026-09-26 03:00').waitFor({ timeout: 10000 })
  check("extension reads data through the host's useMethodRead (frappe-ui useCall)", true)
  check('setTitle() from the extension reaches the host document', (await page.title()) === 'Printful')

  // 3. A toast raised inside the extension renders in the host's toaster: only
  //    possible when both share one frappe-ui (vue-sonner state is module-level).
  await page.getByRole('button', { name: 'Sync now' }).click()
  const toast = page.getByText('Printful sync started')
  await toast.waitFor({ timeout: 10000 })
  check("extension toast shows in the host's toaster (one frappe-ui instance)", await toast.isVisible())
  await page.screenshot({ path: 'screenshots/2-app-page-toast.png' })
  await page.getByRole('button', { name: 'Direct toast' }).click()
  const directToast = page.getByText('Toast via frappe-ui import')
  await directToast.waitFor({ timeout: 10000 })
  check("toast imported straight from 'frappe-ui' also reaches the host's toaster", await directToast.isVisible())

  // 4. frappe-ui Dialog from the extension opens in the host's overlay layer.
  await page.getByRole('button', { name: 'Clear stuck sync' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.waitFor({ timeout: 10000 })
  await dialog.getByPlaceholder('CLEAR').fill('CLEAR')
  await page.screenshot({ path: 'screenshots/3-dialog.png' })
  await dialog.getByRole('button', { name: 'Clear' }).click()
  await page.getByText('Stuck sync cleared').waitFor({ timeout: 10000 })
  check('extension Dialog opens, takes input, and closes through host overlays', true)

  // 5. navigate() keeps the extension inside its own base path.
  await page.getByRole('button', { name: 'Open syncs sub-page' }).click()
  await page.getByText('Sub-path: syncs').waitFor({ timeout: 10000 })
  check('navigate() routes to a sub-path under /apps/printful/printful/', page.url().endsWith('/apps/printful/printful/syncs'))

  checkSingleRuntime('first page load')
  requests.length = 0

  // 6. Record block gets the host's provide()d context (same Vue, same @commera/admin),
  //    and a broken extension on the same page is contained to one card.
  await page.goto(`${BASE}/orders/SO-1001`)
  const block = page.locator('[data-printful-block]')
  await block.waitFor({ timeout: 10000 })
  check('order block receives resource via inject() across separate builds', (await block.textContent()).includes('SO-1001'))
  const failure = page.locator('[data-extension-failure]')
  await failure.waitFor({ timeout: 10000 })
  check('broken extension shows a failure card', (await failure.textContent()).includes('deliberately broken'))
  check('host page still renders next to the broken extension', await page.getByText('host-rendered order lines').isVisible())
  await page.screenshot({ path: 'screenshots/4-order-blocks.png' })

  // 7. Nothing loaded a second Vue or frappe-ui.
  checkSingleRuntime('order page load')
  const appRequests = requests.filter((path) => /^\/assets\/(printful|broken)\//.test(path))
  const bytes = appRequests.map((path) => statSync(`apps/${path.split('/')[2]}/dist/${path.split('/commera/')[1]}`).size)
  check('extension bundles carry only their own code', Math.max(...bytes) < 10_000, `largest ${Math.max(...bytes)} bytes`)
  check('no uncaught page errors', pageErrors.length === 0, pageErrors.join(' | '))
} catch (error) {
  check('run completed', false, error.message)
  await page.screenshot({ path: 'screenshots/error.png' })
} finally {
  await browser.close()
  server.kill()
}

const failed = results.filter((result) => !result.ok).length
console.log(`\n${results.length - failed}/${results.length} checks passed`)
process.exit(failed ? 1 : 0)
