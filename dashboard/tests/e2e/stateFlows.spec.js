// Flows whose correctness depends on request timing: a late answer must not overwrite newer
// state, and an action must not run twice. Each test holds one request open with Puppeteer's
// request interception, does the thing a merchant does while it hangs, then lets it land.
// Read-only: nothing here is allowed to reach a write endpoint.
import assert from 'node:assert/strict'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe } from 'node:test'
import { PREFIX, RUN_ID, adminGet, adminPost, clickByText, findByText, goto, onCleanup, text, uiTest, useSession, wait } from './harness.js'

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

async function typeIntoFirst(page, placeholder, value) {
  const input = await page.$(`input[placeholder="${placeholder}"]`)
  if (!input) throw new Error('no input with placeholder ' + placeholder)
  await input.click()
  await input.type(value)
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

  uiTest(session, 'bulk fulfil: one run at a time, a refusal does not stop it, and the list reloads', async () => {
    const { page } = session
    await goto(page, '/orders')
    await clickByText(page, 'button', 'Select')
    const rows = await page.$$('a[data-slot=list-row]')
    assert.ok(rows.length >= 2, 'needs two orders on the first page')
    await rows[0].click()
    await rows[1].click()
    await wait(300)

    // Never reaches the server: the first order "fulfils", the second is refused.
    const fulfils = []
    let listReads = 0
    const onRequest = (request) => {
      if (request.isInterceptResolutionHandled()) return
      if (request.url().includes('orders.get_orders')) listReads += 1
      if (!request.url().includes('orders.fulfil_order')) return request.continue()
      fulfils.push(request.postData())
      const refused = fulfils.length === 2
      setTimeout(() => {
        request.respond(
          refused
            ? {
                status: 417,
                contentType: 'application/json',
                body: JSON.stringify({ errors: [{ type: 'ValidationError', message: 'Order is on hold' }] }),
              }
            : { status: 200, contentType: 'application/json', body: JSON.stringify({ data: {} }) },
        )
      }, 400)
    }
    await page.setRequestInterception(true)
    page.on('request', onRequest)
    try {
      const button = await findByText(page, 'button', 'Mark fulfilled')
      await button.click()
      await button.click({ delay: 0 }).catch(() => {})
      await waitFor(async () => (await text(page)).includes('failed'), { label: 'the summary toast' })
      await wait(800)
      assert.equal(fulfils.length, 2, `a second click started another run: ${fulfils.length} fulfil calls`)
      const body = await text(page)
      assert.ok(body.includes('1 of 2 orders marked fulfilled. 1 failed: Order is on hold'), 'no partial-failure summary: ' + (await page.evaluate(() => [...document.querySelectorAll('[data-sonner-toast]')].map((t) => t.innerText).join(' / '))))
      assert.ok(listReads >= 1, 'the list was not reloaded after the run')
      assert.ok(body.includes('1 order selected'), 'the refused order should stay selected for a retry')
    } finally {
      page.off('request', onRequest)
      await page.setRequestInterception(false)
    }
  })

  uiTest(session, 'variant save: a double click receives stock once', async () => {
    const { page } = session
    const { products } = await adminGet(page, 'catalog.get_products', { page_length: 20 })
    let target = null
    for (const listed of products) {
      const product = await adminGet(page, 'catalog.get_product', { item_template: listed.name })
      const variant = product.variants.find((candidate) => candidate.sizes.length)
      if (variant) {
        target = { product: product.name ?? listed.name, variant: variant.name }
        break
      }
    }
    assert.ok(target, 'needs a product with a sized variant')
    await goto(page, `/products/${encodeURIComponent(target.product)}/variants/${encodeURIComponent(target.variant)}`)

    // Never reaches the server: both writes answer after a beat, as a slow site would.
    const writes = { prices: 0, receipts: 0 }
    const onRequest = (request) => {
      if (request.isInterceptResolutionHandled()) return
      const url = request.url()
      const kind = url.includes('catalog.save_product_prices') ? 'prices' : url.includes('catalog.receive_product_stock') ? 'receipts' : null
      if (!kind) return request.continue()
      writes[kind] += 1
      setTimeout(() => request.respond({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: {} }) }), 500)
    }
    await page.setRequestInterception(true)
    page.on('request', onRequest)
    try {
      await typeIntoFirst(page, 'Receive qty', '2')
      const save = await findByText(page, 'button', 'Save')
      await save.click()
      await save.click().catch(() => {})
      await save.click().catch(() => {})
      await waitFor(async () => (await text(page)).includes('Variant saved'), { label: 'the save toast' })
      await wait(800)
      assert.equal(writes.prices, 1, `prices were written ${writes.prices} times`)
      assert.equal(writes.receipts, 1, `stock was received ${writes.receipts} times`)
    } finally {
      page.off('request', onRequest)
      await page.setRequestInterception(false)
    }
  })

  uiTest(session, 'discount editor: no false unsaved prompt, edits are guarded, and Save and Active never overlap', async () => {
    const { page } = session
    const discount = await adminPost(page, 'discounts.save_discount', {
      discount: {
        title: `${PREFIX} Discount`,
        code: `E2E${RUN_ID}`,
        method: 'Code',
        discount_type: 'Amount Off Order',
        enabled: 1,
        value_type: 'Percentage',
        value: 5,
      },
    })
    onCleanup(session, ({ page: cleanupPage }) => adminPost(cleanupPage, 'discounts.delete_discount', { name: discount.name }))
    page.removeAllListeners('dialog')
    page.on('dialog', (dialog) => dialog.accept())

    // Opened and left untouched: leaving must not ask.
    await goto(page, `/discounts/${encodeURIComponent(discount.name)}`)
    await waitFor(async () => (await text(page)).includes('Setup'), { label: 'the editor' })
    const push = (path) =>
      page.evaluate((target) => document.querySelector('#app').__vue_app__.config.globalProperties.$router.push(target), path)
    await push('/discounts')
    await wait(800)
    assert.ok(!(await text(page)).includes('Discard unsaved changes?'), 'an untouched discount asked about unsaved changes')
    assert.ok(page.url().endsWith('/discounts'), 'leaving an untouched discount was blocked')

    // Edited: leaving asks, and Cancel stays.
    await goto(page, `/discounts/${encodeURIComponent(discount.name)}`)
    await waitFor(async () => (await text(page)).includes('Setup'), { label: 'the editor' })
    // The value box: the discount was made at 5%.
    const valueBox = (
      await page.evaluateHandle(() => [...document.querySelectorAll('input')].find((input) => input.value === '5'))
    ).asElement()
    assert.ok(valueBox, 'no value box')
    await valueBox.click()
    await valueBox.type('0')
    push('/discounts').catch(() => {})
    await waitFor(async () => (await text(page)).includes('Discard unsaved changes?'), { label: 'the unsaved prompt' })
    await clickByText(page, '[role=dialog] button', 'Cancel')
    assert.ok(page.url().includes(`/discounts/${encodeURIComponent(discount.name)}`), 'Cancel left the editor')

    // Save and the Active switch write through one request: while one runs the other is shut.
    const writes = []
    const onRequest = (request) => {
      if (request.isInterceptResolutionHandled()) return
      if (!request.url().includes('discounts.save_discount')) return request.continue()
      writes.push(request.postData())
      setTimeout(() => request.continue(), 800)
    }
    await page.setRequestInterception(true)
    page.on('request', onRequest)
    try {
      await clickByText(page, 'button', 'Save', { pause: 50 })
      const toggle = await page.$('button[role=switch]')
      await toggle.click().catch(() => {})
      await waitFor(async () => (await text(page)).includes('Saved'), { label: 'the save toast' })
      await wait(1200)
      assert.equal(writes.length, 1, `Save and Active overlapped: ${writes.length} writes`)
    } finally {
      page.off('request', onRequest)
      await page.setRequestInterception(false)
    }
  })
})
