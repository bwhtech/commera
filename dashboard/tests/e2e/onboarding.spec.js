// Write lane over the first-run onboarding, end to end with real clicks. Works on a fresh site,
// where the store setup really runs ERPNext's setup in the background, and on a store that is
// already set up, where the spec reopens onboarding by clearing the flag and puts it all back after.
import assert from 'node:assert/strict'
import { before, describe } from 'node:test'
import { PREFIX, adminGet, adminPost, clickByText, goto, onCleanup, realProblems, text, uiTest, useSession, wait } from './harness.js'

const STORE_NAME = `${PREFIX} Store`
const SETTINGS = 'Commera Settings'
const STEP_KEY = 'commera:onboarding-step'
// ERPNext's setup builds the chart of accounts, warehouses and fixtures in a background job.
const SETUP_TIMEOUT = 180000
const PASSWORD = process.env.COMMERA_PASSWORD || 'Admin123'

// The single's own document over REST v2, the same session the dashboard runs as.
async function readSettings(page) {
  return page.evaluate(async (doctype) => {
    const path = `/api/v2/document/${encodeURIComponent(doctype)}/${encodeURIComponent(doctype)}`
    const reply = await fetch(path, { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
    if (!reply.ok) throw new Error(`GET ${doctype} -> HTTP ${reply.status}`)
    return (await reply.json()).data
  }, SETTINGS)
}

async function writeSettings(page, values) {
  const response = await page.evaluate(
    async (doctype, payload) => {
      const path = `/api/v2/document/${encodeURIComponent(doctype)}/${encodeURIComponent(doctype)}`
      const reply = await fetch(path, {
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
    },
    SETTINGS,
    values,
  )
  if (response.status >= 400) throw new Error(`PUT ${SETTINGS} -> HTTP ${response.status}: ${response.body.slice(0, 300)}`)
}

// The telemetry plugin reads boot_config from the site and imports the Pulse client from its CDN.
// Both are answered here: telemetry turns on, and the stand-in client keeps every capture on
// `window.__pulseEvents` instead of sending it, so the spec sees exactly what left the browser.
const BOOT_CONFIG = '/api/method/frappe.utils.telemetry.pulse.client.boot_config'
const PULSE_CLIENT = 'https://pulse.m.frappe.cloud/assets/pulse/js/pulse_client.js'
const PULSE_STAND_IN = `export class PulseClient {
  async init() { return true }
  setEnabled() {}
  capture(event, app, props = {}) { (window.__pulseEvents ||= []).push({ event, app, props }) }
  getDistinctId() { return '' }
  flush() {}
  stop() {}
}`

async function stubPulse(page) {
  // The login already loaded the real client into the HTTP cache, which a cached hit would serve past the stub.
  await page.setCacheEnabled(false)
  await page.setRequestInterception(true)
  page.on('request', (request) => {
    if (request.isInterceptResolutionHandled()) return
    const url = request.url()
    if (url.startsWith(PULSE_CLIENT)) {
      return request.respond({
        contentType: 'application/javascript',
        headers: { 'Access-Control-Allow-Origin': '*' },
        body: PULSE_STAND_IN,
      })
    }
    if (new URL(url).pathname === BOOT_CONFIG) {
      const config = { enabled: true, host: 'https://pulse.invalid', client_url: PULSE_CLIENT, key: 'test', site: 'x', site_age: 1 }
      return request.respond({ contentType: 'application/json', body: JSON.stringify({ message: config }) })
    }
    return request.continue()
  })
}

const pulseEvents = (page) => page.evaluate(() => window.__pulseEvents ?? [])

const stepShown = (page, key) => page.waitForSelector(`[data-onboarding-step="${key}"]`, { visible: true, timeout: 20000 })

async function pressContinue(page, nextKey) {
  await clickByText(page, '[data-onboarding] button', 'Continue', { pause: 300 })
  await stepShown(page, nextKey)
  await wait(400)
}

// The first switch, swatch or theme that is not already the stored choice, so the step really writes.
async function clickUnpressed(page, selector) {
  const handle = await page.$(`${selector}[aria-pressed="false"]`)
  if (!handle) throw new Error(`nothing unpicked matches ${selector}`)
  await handle.click()
  await wait(400)
  return handle
}

async function pickFromCombobox(page, placeholder, value) {
  await clickByText(page, '[data-onboarding-step="store"] button', placeholder)
  await page.keyboard.type(value, { delay: 20 })
  await wait(500)
  await page.keyboard.press('Enter')
  await wait(800)
}

describe('onboarding', () => {
  const session = useSession()
  const original = {}

  before(async () => {
    const { page } = session
    const settings = await readSettings(page)
    const record = await adminGet(page, 'onboarding.get_onboarding')
    const { active_theme: activeTheme } = await adminGet(page, 'theme.get_editor_data')
    Object.assign(original, {
      onboardingCompleted: settings.onboarding_completed ? 1 : 0,
      storeName: settings.store_name || '',
      storeCategory: settings.store_category || '',
      brandLogo: record.brand_logo || '',
      primaryColor: record.primary_color || '',
      codEnabled: record.cod_enabled,
      allowGuestCheckout: record.allow_guest_checkout,
      theme: activeTheme,
      country: record.country,
    })
    if (original.onboardingCompleted) await writeSettings(page, { onboarding_completed: 0 })
    await stubPulse(page)
  })

  onCleanup(session, async ({ page }) => {
    await adminPost(page, 'onboarding.save_brand', { brand_logo: original.brandLogo, primary_color: original.primaryColor })
    await adminPost(page, 'onboarding.save_selling', {
      cod_enabled: original.codEnabled ? 1 : 0,
      allow_guest_checkout: original.allowGuestCheckout ? 1 : 0,
    })
    if (original.theme) await adminPost(page, 'theme.activate_theme', { theme: original.theme })
    await writeSettings(page, {
      store_name: original.storeName,
      store_category: original.storeCategory,
      onboarding_completed: original.onboardingCompleted,
    })
  })

  uiTest(
    session,
    'a new owner steps through onboarding into the dashboard, and it never comes back',
    async () => {
      const { page } = session
      await goto(page, '/')
      await page.evaluate((key) => localStorage.removeItem(key), STEP_KEY)
      await goto(page, '/')
      await page.waitForSelector('[data-onboarding]', { timeout: 20000 })
      await stepShown(page, 'you')

      const password = await page.$('[data-onboarding-step="you"] input[type="password"]')
      if (password) await password.type(PASSWORD, { delay: 10 })
      const fullName = await page.$('[data-onboarding-step="you"] input')
      if (!(await fullName.evaluate((input) => input.value.trim()))) await fullName.type('E2E Owner', { delay: 10 })
      await pressContinue(page, 'store')

      const storeName = await page.$('[data-onboarding-step="store"] input')
      await storeName.click({ count: 3 })
      await storeName.type(STORE_NAME, { delay: 10 })
      await clickByText(page, '[data-onboarding-step="store"] button', 'Fashion')
      if (!original.country) await pickFromCombobox(page, 'Search countries', 'India')

      await page.click('[data-onboarding-accounting]')
      await wait(500)
      assert.equal(await page.$eval('[data-onboarding-accounting]', (button) => button.getAttribute('aria-expanded')), 'true')
      assert.ok((await text(page)).includes('Chart of accounts'), 'the accounting line opens onto the chart of accounts')
      await pressContinue(page, 'brand')

      // Back reverses one step and keeps what was typed.
      await clickByText(page, '[data-onboarding] button', 'Back', { pause: 300 })
      await stepShown(page, 'store')
      assert.equal(await page.$eval('[data-onboarding-step="store"] input', (input) => input.value), STORE_NAME)
      await pressContinue(page, 'brand')

      await page.waitForSelector('[data-onboarding-setup="done"], [data-onboarding-setup="failed"]', { timeout: SETUP_TIMEOUT })
      const failure = await page.$('[data-onboarding-setup="failed"]')
      assert.equal(failure, null, 'the store setup finished: ' + (failure ? await text(page) : ''))

      await clickUnpressed(page, '[data-onboarding-colour]')
      const pickedColour = await page.$eval('[data-onboarding-colour][aria-pressed="true"]', (button) =>
        button.getAttribute('aria-label').replace('Use ', ''),
      )
      await pressContinue(page, 'theme')

      await page.waitForSelector('[data-onboarding-theme]', { timeout: 20000 })
      const themeButton = await clickUnpressed(page, '[data-onboarding-theme]').catch(() => page.$('[data-onboarding-theme]'))
      const pickedTheme = await themeButton.evaluate((button) => button.dataset.onboardingTheme)
      await pressContinue(page, 'selling')

      const guestSwitch = (await page.$$('[data-onboarding-step="selling"] [role="switch"]'))[1]
      await guestSwitch.click()
      await wait(300)
      const guestCheckout = (await guestSwitch.evaluate((element) => element.getAttribute('aria-checked'))) === 'true'
      await pressContinue(page, 'products')

      const shopify = await page.$('[data-onboarding-source="shopify"]')
      assert.ok(await shopify.evaluate((button) => button.disabled), 'Shopify import cannot be started yet')
      assert.ok((await shopify.evaluate((button) => button.innerText)).includes('Coming soon'))
      await page.waitForSelector('[data-onboarding-source="csv"]:not([disabled])', { timeout: 20000 })
      await page.click('[data-onboarding-source="csv"]')
      // The import dialog is bare and not dismissible (Esc would drop a half-mapped file), so it is
      // found by its title and closed with its own Close button.
      const importOpen = () => document.body.innerText.includes('Import products')
      await page.waitForFunction(importOpen, { timeout: 10000 })
      await page.click('button[aria-label="Close"]')
      await page.waitForFunction((title) => !document.body.innerText.includes(title), { timeout: 10000 }, 'Import products')
      await clickByText(page, '[data-onboarding] button', 'Skip', { pause: 300 })
      await stepShown(page, 'done')
      assert.ok((await text(page)).includes(`${STORE_NAME} is live`))

      // Read before the dashboard opens: a reload there would clear the page's record.
      const events = await pulseEvents(page)
      assert.ok(events.length && events.every((entry) => entry.app === 'commera'), 'every event is sent as commera')
      const named = (name) => events.filter((entry) => entry.event === name).map((entry) => entry.props)
      assert.deepEqual(
        named('onboarding_started').map(({ step, resumed }) => ({ step, resumed })),
        [{ step: 'you', resumed: false }],
      )
      assert.deepEqual(
        named('onboarding_step_completed').map(({ step, action }) => `${step}:${action}`),
        ['you:continue', 'store:continue', 'store:continue', 'brand:continue', 'theme:continue', 'selling:continue', 'products:skip'],
      )
      assert.ok(named('onboarding_step_completed').every((props) => /^(lt_10s|10_30s|30_120s|gt_120s)$/.test(props.duration_bucket)))
      assert.deepEqual(named('onboarding_back_pressed').map(({ step }) => step), ['brand'])
      assert.equal(named('onboarding_accounting_opened').length, 1)
      assert.deepEqual(named('products_import_opened').map(({ surface }) => surface), ['onboarding'])
      assert.ok(named('pageview').every((props) => !String(props.route).includes(STORE_NAME)), 'a pageview sends the route pattern only')
      assert.ok(!JSON.stringify(events).includes(STORE_NAME), 'no event carries the store name')

      await clickByText(page, '[data-onboarding] button', 'Go to dashboard', { pause: 300 })
      // A store whose currency changed reloads into the dashboard instead of switching in place.
      await page.waitForFunction(
        () => !document.querySelector('[data-onboarding]') && document.body.innerText.includes('Orders'),
        { timeout: 30000 },
      )
      await wait(1500)
      assert.ok(!(await text(page)).includes(`${STORE_NAME} is live`), 'the dashboard replaced onboarding')

      const settings = await readSettings(page)
      assert.equal(settings.store_name, STORE_NAME)
      assert.equal(settings.store_category, 'Fashion')
      assert.equal(Boolean(settings.onboarding_completed), true)
      const record = await adminGet(page, 'onboarding.get_onboarding')
      assert.equal(record.primary_color, pickedColour)
      assert.equal(record.allow_guest_checkout, guestCheckout)
      assert.equal((await adminGet(page, 'theme.get_editor_data')).active_theme, pickedTheme)

      await goto(page, '/')
      assert.equal(await page.$('[data-onboarding]'), null, 'a reload opens the dashboard, not onboarding')

      assert.deepEqual(realProblems(session.problems), [])
    },
    { timeout: SETUP_TIMEOUT + 120000 },
  )
})
