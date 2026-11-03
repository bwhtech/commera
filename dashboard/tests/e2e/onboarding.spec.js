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

// Every dashboard event posts to Commera's own record_event, and only when the boot says telemetry
// is on. The boot key is turned on in the page, each post is recorded here, and the request still
// goes to the server, so the server's refusal of an unknown event would fail the spec.
const RECORD_EVENT = '/api/v2/method/commera.api.admin.telemetry.record_event'

async function recordTelemetry(page) {
  const posted = []
  await page.evaluateOnNewDocument(() => {
    let boot
    Object.defineProperty(window, 'telemetry', {
      configurable: true,
      get: () => boot,
      set: () => (boot = { enabled: true, site_age: 1 }),
    })
  })
  await page.setRequestInterception(true)
  page.on('request', (request) => {
    if (request.isInterceptResolutionHandled()) return
    if (new URL(request.url()).pathname === RECORD_EVENT) posted.push(JSON.parse(request.postData() || '{}'))
    return request.continue()
  })
  return posted
}

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
  let telemetryEvents = []

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
    telemetryEvents = await recordTelemetry(page)
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

      // An owner does not wait for the store setup: brand, theme and selling save while it still runs,
      // which is what a setup job holding a stale copy of Commera Settings would trip over.
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
      // The products step needs the store: its CSV import waits for the setup to finish.
      await page.waitForSelector('[data-onboarding-setup="done"], [data-onboarding-setup="failed"]', { timeout: SETUP_TIMEOUT })
      const failure = await page.$('[data-onboarding-setup="failed"]')
      assert.equal(failure, null, 'the store setup finished: ' + (failure ? await text(page) : ''))

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

      const sent = (name) => telemetryEvents.filter((entry) => entry.event === name).map((entry) => entry.properties)
      assert.deepEqual(sent('products_import_opened').map(({ surface }) => surface), ['onboarding'])
      assert.ok(sent('pageview').length, 'a new site sends page views')
      assert.ok(sent('pageview').every(({ route }) => route.startsWith('/') && !route.includes(STORE_NAME)))

      // The funnel, named as Frappe's setup wizard names its own.
      // The spec's own reload at the start left the first onboarding page open on `you`.
      assert.deepEqual(sent('left_setup').map(({ step }) => step), ['you'])
      // Once for the page the reload left, once for the run itself.
      assert.equal(sent('started_setup').length, 2)
      const { step: startStep, resumed, total_steps: totalSteps } = sent('started_setup').at(-1)
      assert.deepEqual({ startStep, resumed, totalSteps }, { startStep: 'you', resumed: false, totalSteps: 7 })
      assert.deepEqual(
        sent('completed_setup_step').map(({ step, step_number }) => `${step_number}:${step}`),
        ['1:you', '2:store', '2:store', '3:brand', '4:theme', '5:selling'],
      )
      assert.deepEqual(sent('skipped_setup_step').map(({ step }) => step), ['products'])
      assert.ok(
        [...sent('completed_setup_step'), ...sent('skipped_setup_step')].every(
          (properties) => properties.total_steps === 7 && Number.isInteger(properties.duration_seconds),
        ),
      )
      assert.deepEqual(sent('went_back_in_setup'), [{ from_step: 'brand', to_step: 'store' }])
      assert.equal(sent('onboarding_accounting_opened').length, 1)
      assert.ok(!JSON.stringify(telemetryEvents).includes(STORE_NAME), 'no event carries the store name')

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
