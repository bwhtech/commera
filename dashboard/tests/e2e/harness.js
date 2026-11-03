// Shared puppeteer harness for the Commera dashboard end-to-end suite.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { after, before, test } from 'node:test'
import puppeteer from 'puppeteer'

const HERE = path.dirname(fileURLToPath(import.meta.url))

// The public HTTPS host is currently served through a proxy with a broken TLS
// chain, so the suite defaults to the bench webserver and the URL stays an override.
export const BASE = process.env.COMMERA_BASE || 'http://dev.localhost:8000'

const USER = process.env.COMMERA_USER || 'Administrator'
const PASSWORD = process.env.COMMERA_PASSWORD || 'Admin123'

export const ARTIFACTS = process.env.COMMERA_ARTIFACTS || path.join(HERE, '.artifacts')
const COOKIE_FILE = path.join(ARTIFACTS, 'session.json')

// Every row the suite writes carries this, so a teardown (or a human) can find
// and archive exactly what this run made and nothing else.
export const RUN_ID = process.env.COMMERA_RUN_ID || Math.random().toString(36).slice(2, 8).toUpperCase()
export const PREFIX = `E2E-${RUN_ID}`

export function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function readCookies() {
  try {
    return JSON.parse(fs.readFileSync(COOKIE_FILE, 'utf8'))
  } catch {
    return null
  }
}

function writeCookies(cookies) {
  fs.mkdirSync(ARTIFACTS, { recursive: true })
  fs.writeFileSync(COOKIE_FILE, JSON.stringify(cookies, null, 2))
}

// `anonymous` opens a browser with no stored cookies and no login: the storefront
// flows have to start as a guest shopper.
export async function openSession({ mobile = false, anonymous = false } = {}) {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
  })
  const page = await browser.newPage()
  await page.setViewport(mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 })

  const problems = []
  page.on('console', (message) => {
    if (message.type() === 'error') problems.push('CONSOLE: ' + message.text())
  })
  page.on('pageerror', (error) => problems.push('PAGEERROR: ' + error.message))
  page.on('requestfailed', (request) => {
    problems.push('REQFAIL: ' + request.url() + ' ' + (request.failure() || {}).errorText)
  })
  page.on('response', (response) => {
    if (response.status() >= 400) problems.push('HTTP ' + response.status() + ': ' + response.url())
  })

  const session = { browser, page, problems }
  if (!anonymous) await login(session)
  return session
}

export async function closeSession(session) {
  if (session?.browser) await session.browser.close()
}

// Cookies are cached on disk and reused: a fresh form login per spec file roughly
// doubles the suite's runtime for no extra coverage.
async function login(session) {
  const { page, problems } = session
  const cached = readCookies()
  if (cached?.length) {
    await page.browser().setCookie(...cached)
    await page.goto(BASE + '/commera/', { waitUntil: 'networkidle2', timeout: 60000 })
    if (!page.url().includes('/login')) {
      problems.length = 0
      return
    }
  }

  await page.goto(BASE + '/login?redirect-to=/commera', { waitUntil: 'networkidle2', timeout: 60000 })
  if (page.url().includes('/login')) {
    await page.type('#login_email', USER)
    await page.type('#login_password', PASSWORD)
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 60000 }).catch(() => {}),
      // Frappe's login page dropped the `.btn-login` class; the sign-in form is
      // `.form-login` and the other `type=submit` buttons belong to the hidden
      // forgot-password and email-link forms, so scope the click to that form.
      page.click('.form-login button[type="submit"]'),
    ])
  }
  if (page.url().includes('/login')) throw new Error('login failed at ' + BASE)
  writeCookies(await page.browser().cookies())
  // Frappe's own /desk landing requests a broken splash image, so the login hop's
  // noise is discarded rather than reported as a dashboard problem.
  problems.length = 0
}

export async function goto(page, route) {
  await page.goto(BASE + '/commera' + route, { waitUntil: 'networkidle2', timeout: 60000 })
  await wait(1200)
}

export async function text(page) {
  return page.evaluate(() => document.body.innerText)
}

export async function shot(page, name) {
  fs.mkdirSync(ARTIFACTS, { recursive: true })
  const file = path.join(ARTIFACTS, name.replace(/[^\w.-]+/g, '_') + '.png')
  await page.screenshot({ path: file, fullPage: false })
  return file
}

export async function findByText(page, selector, label, { exact = true, last = false } = {}) {
  const handle = await page.evaluateHandle(
    (sel, needle, isExact, wantLast) => {
      const matches = Array.from(document.querySelectorAll(sel)).filter((element) => {
        if (element.offsetParent === null && getComputedStyle(element).position !== 'fixed') return false
        const value = (element.innerText || element.textContent || '').trim()
        return isExact ? value === needle : value.includes(needle)
      })
      return wantLast ? matches[matches.length - 1] : matches[0]
    },
    selector,
    label,
    exact,
    last,
  )
  return handle.asElement()
}

// Always a real mouse click on the element handle: frappe-ui widgets (Select,
// Autocomplete, Dropdown) listen for pointer events that an in-page el.click() never fires.
export async function clickByText(page, selector, label, options = {}) {
  const element = await findByText(page, selector, label, options)
  if (!element) throw new Error(`no visible ${selector} labelled "${label}"`)
  await element.click()
  await wait(options.pause ?? 600)
  return element
}

export async function typeInto(page, placeholder, value) {
  const handle = await page.evaluateHandle(
    (needle) =>
      Array.from(document.querySelectorAll('input, textarea')).find(
        (element) => element.placeholder === needle && element.offsetParent !== null,
      ),
    placeholder,
  )
  const element = handle.asElement()
  if (!element) throw new Error('no visible input with placeholder ' + placeholder)
  await element.click()
  await element.type(value, { delay: 15 })
  return element
}

function unwrap(response, label) {
  if (response.status >= 400) throw new Error(`${label} -> HTTP ${response.status}: ${response.body.slice(0, 400)}`)
  const parsed = JSON.parse(response.body)
  return parsed.data ?? parsed.message ?? parsed
}

// Server state is asserted over the same admin API the dashboard itself calls,
// reusing the browser's logged-in cookies, so a spec never shells out to bench.
export async function adminGet(page, method, params = {}) {
  return apiGet(page, 'commera.api.admin.' + method, params)
}

export async function adminPost(page, method, body = {}) {
  return apiPost(page, 'commera.api.admin.' + method, body)
}

export async function apiGet(page, method, params = {}) {
  const response = await page.evaluate(async (path, query) => {
    const url = '/api/v2/method/' + path + '?' + new URLSearchParams(query).toString()
    const reply = await fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
    return { status: reply.status, body: await reply.text() }
  }, method, serialise(params))
  return unwrap(response, 'GET ' + method)
}

export async function apiPost(page, method, body = {}) {
  const response = await page.evaluate(async (path, payload) => {
    const reply = await fetch('/api/v2/method/' + path, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': window.csrf_token || '',
      },
      body: JSON.stringify(payload),
    })
    return { status: reply.status, body: await reply.text() }
  }, method, body)
  return unwrap(response, 'POST ' + method)
}

// Cleanup only. There is no admin endpoint to delete a collection or an attribute,
// so teardown falls back to the generic resource API as the logged-in Administrator.
export async function deleteResource(page, doctype, name) {
  const response = await page.evaluate(async (type, docname) => {
    const reply = await fetch(`/api/resource/${encodeURIComponent(type)}/${encodeURIComponent(docname)}`, {
      method: 'DELETE',
      credentials: 'same-origin',
      headers: { Accept: 'application/json', 'X-Frappe-CSRF-Token': window.csrf_token || '' },
    })
    return { status: reply.status, body: await reply.text() }
  }, doctype, name)
  return unwrap(response, 'DELETE ' + doctype + '/' + name)
}

export async function listResource(page, doctype, filters = {}, fields = ['name']) {
  const response = await page.evaluate(async (type, query) => {
    const reply = await fetch(`/api/resource/${encodeURIComponent(type)}?` + new URLSearchParams(query).toString(), {
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
    })
    return { status: reply.status, body: await reply.text() }
  }, doctype, { filters: JSON.stringify(filters), fields: JSON.stringify(fields), limit_page_length: '0' })
  return unwrap(response, 'LIST ' + doctype)
}

export async function updateResource(page, doctype, name, values) {
  const response = await page.evaluate(async (type, docname, payload) => {
    const reply = await fetch(`/api/resource/${encodeURIComponent(type)}/${encodeURIComponent(docname)}`, {
      method: 'PUT',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': window.csrf_token || '',
      },
      body: JSON.stringify(payload),
    })
    return { status: reply.status, body: await reply.text() }
  }, doctype, name, values)
  return unwrap(response, 'PUT ' + doctype + '/' + name)
}

function serialise(params) {
  const out = {}
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue
    out[key] = typeof value === 'object' ? JSON.stringify(value) : String(value)
  }
  return out
}

// A spec file shares one browser: `before` logs in once, `after` closes it.
export function useSession(options = {}) {
  const session = { cleanups: [] }
  before(async () => {
    Object.assign(session, await openSession(options))
  })
  // Teardown runs before the browser closes, because it drives the admin API through
  // the page's own logged-in session.
  after(async () => {
    for (const cleanup of session.cleanups) {
      await cleanup(session).catch((error) => console.error('cleanup failed:', error.message))
    }
    await closeSession(session)
  })
  return session
}

// Registers work to undo at the end of the spec file. Every row the suite creates
// must be registered here so the store does not silently fill with E2E- junk.
export function onCleanup(session, fn) {
  session.cleanups.push(fn)
}

// Wraps node:test so a failure leaves one screenshot, named for the test, in the
// gitignored artifacts directory — and nothing at all when the test passes.
export function uiTest(session, name, fn, { timeout = 120000 } = {}) {
  test(name, { timeout }, async (t) => {
    session.problems.length = 0
    try {
      await fn(t)
    } catch (error) {
      await shot(session.page, 'FAIL-' + name).catch(() => {})
      throw error
    }
  })
}

// favicon 404s come from the Frappe shell, not the dashboard, and are not a defect.
// Test benches run on Pilot, which writes the credentials that make Frappe call a site "Frappe
// Cloud v2" but has no Cloud behind it, so the trial card's one billing read is refused (417).
// That refusal is the bench's, not the dashboard's; the browser echoes it as a console line.
const BILLING_READ = 'cloud_settings.get_billing'

export function realProblems(problems) {
  const unique = [...new Set(problems)].filter((entry) => !entry.includes('favicon'))
  const billingRefused = unique.some((entry) => entry.startsWith('HTTP 417') && entry.includes(BILLING_READ))
  return unique.filter((entry) => {
    if (!billingRefused) return true
    if (entry.includes(BILLING_READ)) return false
    return !entry.includes('status of 417')
  })
}
