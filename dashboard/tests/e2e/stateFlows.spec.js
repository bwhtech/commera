// Flows whose correctness depends on request timing: a late answer must not overwrite newer
// state, and an action must not run twice. Each test holds one request open with Puppeteer's
// request interception, does the thing a merchant does while it hangs, then lets it land.
// Read-only: nothing here is allowed to reach a write endpoint.
import assert from 'node:assert/strict'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe } from 'node:test'
import { adminGet, clickByText, findByText, goto, text, uiTest, useSession, wait } from './harness.js'

const HERE = path.dirname(fileURLToPath(import.meta.url))

// Holds every request whose URL matches until `release()`. Interception is switched on per test
// and off again in `stop()`, so the rest of the suite sees an untouched page.
async function holdRequests(page, matches) {
  const held = []
  let holding = true
  const onRequest = (request) => {
    if (request.isInterceptResolutionHandled()) return
    if (holding && matches(request.url(), request)) held.push(request)
    else request.continue()
  }
  await page.setRequestInterception(true)
  page.on('request', onRequest)
  return {
    held,
    async release() {
      holding = false
      for (const request of held.splice(0)) await request.continue().catch(() => {})
    },
    async stop() {
      holding = false
      for (const request of held.splice(0)) await request.continue().catch(() => {})
      page.off('request', onRequest)
      await page.setRequestInterception(false)
    },
  }
}

// Answers every request whose URL contains a key with that key's `data`, as /api/v2 would, so a
// test can put the dashboard in a server state (a setup still running) without making it real.
async function fakeAnswers(page, answers) {
  const onRequest = (request) => {
    if (request.isInterceptResolutionHandled()) return
    const key = Object.keys(answers).find((needle) => request.url().includes(needle))
    if (!key) return request.continue()
    request.respond({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: answers[key] }) })
  }
  await page.setRequestInterception(true)
  page.on('request', onRequest)
  return async () => {
    page.off('request', onRequest)
    await page.setRequestInterception(false)
  }
}

async function writeSettings(page, values) {
  const status = await page.evaluate(async (payload) => {
    const reply = await fetch('/api/v2/document/Commera%20Settings/Commera%20Settings', {
      method: 'PUT',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': window.csrf_token || '' },
      body: JSON.stringify(payload),
    })
    return reply.status
  }, values)
  assert.equal(status, 200, 'could not write Commera Settings')
}

async function waitFor(check, { timeout = 10000, label = 'condition' } = {}) {
  const started = Date.now()
  while (Date.now() - started < timeout) {
    if (await check()) return
    await wait(150)
  }
  throw new Error('timed out waiting for ' + label)
}

// An icon-only frappe-ui Button carries its label as aria-label, not as text.
async function clickLabelled(page, label) {
  const element = await page.$(`[role=dialog] button[aria-label="${label}"]`)
  if (!element) throw new Error(`no button labelled ${label}`)
  await element.click()
  await wait(600)
}

describe('state flows', () => {
  const session = useSession()

  uiTest(session, 'import: a spreadsheet still uploading when the dialog is closed does not land in the reopened one', async () => {
    const { page } = session
    await goto(page, '/products')
    await clickByText(page, 'button', 'Import')
    await clickByText(page, 'button', 'Continue')
    const hold = await holdRequests(page, (url) => url.includes('/api/method/upload_file'))
    try {
      const input = await page.$('input[type=file][accept=".csv,.xlsx"]')
      await input.uploadFile(path.join(HERE, 'fixtures/import-two-rows.csv'))
      await waitFor(async () => hold.held.length > 0, { label: 'the held upload' })
      assert.ok((await text(page)).includes('Reading rows'), 'the upload step did not show it was reading')

      // Every way forward or back is shut while the file is read.
      const back = await findByText(page, 'button', 'Back')
      assert.equal(await back.evaluate((element) => element.disabled), true, 'Back was usable while parsing')

      await clickLabelled(page, 'Close')
      await clickByText(page, 'button', 'Import')
      await hold.release()
      await wait(2500)
      const body = await text(page)
      assert.ok(body.includes('Step 1 of 6'), 'the reopened dialog did not start fresh')
      await clickByText(page, 'button', 'Continue')
      const after = await text(page)
      assert.ok(after.includes('Drop your spreadsheet here'), 'the late upload wrote its file into the fresh dialog')
      assert.ok(!after.includes('import-two-rows.csv'), 'the late upload wrote its file name into the fresh dialog')
    } finally {
      await hold.stop()
      await clickLabelled(page, 'Close').catch(() => {})
    }
  })

  uiTest(session, 'onboarding: the store name is locked while the store setup runs', async () => {
    const { page } = session
    await goto(page, '/')
    const record = await adminGet(page, 'onboarding.get_onboarding')
    const running = { status: 'running', error: '' }
    await writeSettings(page, { onboarding_completed: 0 })
    const stop = await fakeAnswers(page, {
      'onboarding.get_onboarding': { ...record, setup: running },
      'onboarding.get_setup_status': running,
    })
    try {
      await page.evaluate(() => localStorage.setItem('commera:onboarding-step', '1'))
      await goto(page, '/')
      await waitFor(async () => (await text(page)).includes('Your store'), { label: 'the store step' })
      const nameDisabled = await page.evaluate(
        () => [...document.querySelectorAll('[data-onboarding-step=store] input')].find((input) => input.autocomplete === 'organization')?.disabled,
      )
      assert.equal(nameDisabled, true, 'the store name could be edited while setup runs')
      const categoriesDisabled = await page.evaluate(() =>
        [...document.querySelectorAll('[data-onboarding-step=store] button[aria-pressed]')].every((button) => button.disabled),
      )
      assert.equal(categoriesDisabled, true, 'the category could be changed while setup runs')
      assert.ok((await text(page)).includes('once setup finishes'), 'the lock is not explained')
    } finally {
      await stop()
      await writeSettings(page, { onboarding_completed: 1 })
      await page.evaluate(() => localStorage.removeItem('commera:onboarding-step'))
    }
  })
})
