// Storefront discount journeys only a browser shows: codes from a cart link or the promo box reach
// the order, `mode=add` keeps the cart, and signing in merges a guest's cart into the account's.
import assert from 'node:assert/strict'
import { describe } from 'node:test'
import {
  BASE,
  PREFIX,
  adminPost,
  apiPost,
  closeSession,
  deleteResource,
  listResource,
  onCleanup,
  openSession,
  text,
  uiTest,
  updateResource,
  useSession,
  wait,
} from './harness.js'

const CODE = `${PREFIX}-TEN`.toUpperCase()
const SHOPPER_PASSWORD = `E2e-${PREFIX}-pass!`

const created = { orders: [], discounts: [], users: [], theme: null }

async function findStockedItems(page, count) {
  const settings = await apiPost(page, 'frappe.client.get_value', {
    doctype: 'Commera Settings',
    fieldname: ['ecommerce_warehouse'],
  })
  const bins = await listResource(
    page,
    'Bin',
    { warehouse: settings.ecommerce_warehouse, actual_qty: ['>', 5] },
    ['item_code'],
  )
  const published = await listResource(page, 'Style Attribute Variant Size', {}, ['item_code']).catch(() => [])
  const publishedCodes = new Set(published.map((row) => row.item_code))
  const items = bins.map((row) => row.item_code).filter((code) => !publishedCodes.size || publishedCodes.has(code))
  assert.ok(items.length >= count, `need ${count} stocked items in ${settings.ecommerce_warehouse}`)
  return items.slice(0, count)
}

async function ensureOrderCode(page) {
  if (created.discounts.length) return
  const saved = await adminPost(page, 'discounts.save_discount', {
    discount: {
      method: 'Code',
      discount_type: 'Amount Off Order',
      value_type: 'Percentage',
      value: 10,
      code: CODE,
    },
  })
  created.discounts.push(saved.name)
}

// A fresh account each time: a seeded shopper carries carts and codes from earlier runs.
async function createShopper(page, label) {
  const email = `${PREFIX}.${label}@example.com`.toLowerCase()
  await apiPost(page, 'frappe.client.insert', {
    doc: {
      doctype: 'User',
      email,
      first_name: 'E2E',
      last_name: label,
      user_type: 'Website User',
      send_welcome_email: 0,
      new_password: SHOPPER_PASSWORD,
      roles: [{ role: 'Customer' }],
    },
  })
  created.users.push(email)
  return email
}

async function signIn(page, email) {
  const status = await page.evaluate(
    async (usr, pwd) => {
      const reply = await fetch('/api/method/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ usr, pwd }),
      })
      return reply.status
    },
    email,
    SHOPPER_PASSWORD,
  )
  assert.equal(status, 200, `sign-in failed for ${email}`)
}

async function useTheme(page, theme) {
  const settings = await apiPost(page, 'frappe.client.get_value', {
    doctype: 'Shop Theme Settings',
    fieldname: ['active_theme'],
  })
  if (settings.active_theme === theme) return
  created.theme = created.theme || settings.active_theme
  await updateResource(page, 'Shop Theme Settings', 'Shop Theme Settings', { active_theme: theme })
}

async function openCartLink(page, lines, query = {}) {
  const path = lines.map((code) => `${encodeURIComponent(code)}:1`).join(',')
  const search = new URLSearchParams(query).toString()
  await page.goto(`${BASE}/en/cart/${path}${search ? '?' + search : ''}`, { waitUntil: 'networkidle2', timeout: 60000 })
  await page.waitForFunction(() => !location.pathname.match(/\/cart\/[^/]+:\d/), { timeout: 30000 })
  await page.waitForNetworkIdle({ idleTime: 800, timeout: 30000 }).catch(() => {})
}

// The storefront is Alpine-driven, so a value is set through the native setter plus input/change events.
async function setValue(page, selector, value) {
  await page.evaluate(
    (sel, val) => {
      const element = document.querySelector(sel)
      if (!element) throw new Error('setValue: not found ' + sel)
      const prototype = element.tagName === 'SELECT' ? window.HTMLSelectElement : window.HTMLInputElement
      Object.getOwnPropertyDescriptor(prototype.prototype, 'value').set.call(element, val)
      element.dispatchEvent(new Event('input', { bubbles: true }))
      element.dispatchEvent(new Event('change', { bubbles: true }))
    },
    selector,
    value,
  )
}

async function clickByText(page, selector, needle) {
  const handle = await page.evaluateHandle(
    (sel, want) =>
      [...document.querySelectorAll(sel)].find(
        (element) => element.offsetParent !== null && element.textContent.trim().includes(want),
      ),
    selector,
    needle,
  )
  const element = handle.asElement()
  if (!element) throw new Error(`no visible ${selector} containing "${needle}"`)
  await element.click()
}

// The country box is a combobox: a value set without picking an option resolves to another country.
async function pickComboboxOption(page, selector, label) {
  await page.click(selector, { clickCount: 3 })
  await page.type(selector, label)
  await page.waitForFunction(
    (sel, want) =>
      [...document.querySelectorAll(`${sel}_listbox li[role="option"]`)].some((item) => item.textContent.trim() === want),
    { timeout: 15000 },
    selector,
    label,
  )
  const option = await page.evaluateHandle(
    (sel, want) =>
      [...document.querySelectorAll(`${sel}_listbox li[role="option"]`)].find((item) => item.textContent.trim() === want),
    selector,
    label,
  )
  assert.ok(option.asElement(), `no "${label}" option in ${selector}`)
  await option.asElement().click()
}

async function saveSummerAddress(page) {
  const address = {
    first_name: 'E2E',
    last_name: 'Shopper',
    email: `${PREFIX}.guest@example.com`.toLowerCase(),
    phone_number: '+91 98200 12345',
    full_address: '12 Marine Drive',
    landmark: 'Near the station',
    state: 'Maharashtra',
    city: 'Mumbai',
    po_box: '400001',
  }
  // Values typed before Alpine owns the form are wiped when it starts.
  await page.waitForFunction(() => window.Alpine?.$data(document.querySelector('form.row'))?.billing, {
    timeout: 30000,
  })
  for (const [field, value] of Object.entries(address)) await setValue(page, `#billing_${field}`, value)
  await pickComboboxOption(page, '#billing_country', 'India')
  const saved = page.waitForResponse((response) => response.url().includes('update_quotation_address'), {
    timeout: 30000,
  })
  await clickByText(page, 'button[type="submit"]', 'Continue')
  assert.equal((await saved).status(), 200, 'saving the address failed')
  await page.waitForSelector('#payment_mode_cod', { visible: true, timeout: 30000 }).catch(async () => {
    const shown = await page.evaluate(() => {
      const radio = document.querySelector('#payment_mode_cod')
      const payment = document.body.innerText.split('Payment Method')[1] || ''
      return {
        errors: [...document.querySelectorAll('.invalid-feedback, .text-danger, .toast, [role="alert"]')]
          .filter((element) => element.offsetParent !== null)
          .map((element) => element.textContent.trim())
          .filter(Boolean),
        address_saved: window.Alpine?.$data(document.querySelector('form.row'))?.address_saved,
        cod_radio: radio ? (radio.offsetParent === null ? 'hidden' : 'visible') : 'missing',
        payment: payment.slice(0, 200),
      }
    })
    throw new Error(`no payment methods after saving the address; the page says: ${JSON.stringify(shown)}`)
  })
  await page.waitForNetworkIdle({ idleTime: 800, timeout: 30000 }).catch(() => {})
}

async function getShownDiscount(page) {
  return page.evaluate(() => {
    const row = document.querySelector('tr.discount')
    if (!row || row.offsetParent === null) return 0
    return Number(row.querySelector('.price').textContent.replace(/[^\d.]/g, ''))
  })
}

async function placeCodOrder(page) {
  await page.click('#payment_mode_cod')
  await page.click('#accept_terms')
  await clickByText(page, 'button', 'Place Order')
  await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {})
  await wait(1500)
  const match = (await text(page)).match(/Order ID:\s*(\S+)/)
  assert.ok(match, `the confirmation page did not name an order; landed on ${page.url()}`)
  created.orders.push(match[1])
  return match[1]
}

async function getOrder(page, name) {
  return apiPost(page, 'frappe.client.get', { doctype: 'Sales Order', name })
}

async function withGuest(fn) {
  const guest = await openSession({ anonymous: true })
  try {
    await fn(guest.page)
  } finally {
    await closeSession(guest)
  }
}

describe('storefront discounts', () => {
  const admin = useSession()

  onCleanup(admin, async ({ page }) => {
    for (const order of created.orders) {
      for (const event of await listResource(page, 'Storefront Analytics Event', { order_id: order })) {
        await deleteResource(page, 'Storefront Analytics Event', event.name).catch(() => {})
      }
      await apiPost(page, 'frappe.client.cancel', { doctype: 'Sales Order', name: order }).catch(() => {})
      await deleteResource(page, 'Sales Order', order).catch((error) => console.error(error.message))
    }
    // A discount an order used cannot be deleted, and switching it off is what the dashboard offers instead.
    for (const discount of created.discounts) {
      await adminPost(page, 'discounts.delete_discount', { name: discount }).catch(() =>
        updateResource(page, 'Commera Discount', discount, { enabled: 0 }),
      )
    }
    for (const user of created.users) {
      await updateResource(page, 'User', user, { enabled: 0 }).catch(() => {})
    }
    if (created.theme) {
      await updateResource(page, 'Shop Theme Settings', 'Shop Theme Settings', { active_theme: created.theme })
    }
  })

  uiTest(
    admin,
    'a discount code in a cart link is shown at checkout and reaches the order',
    async () => {
      await ensureOrderCode(admin.page)
      const [item] = await findStockedItems(admin.page, 1)

      await withGuest(async (page) => {
        await openCartLink(page, [item], { discount: CODE })
        await saveSummerAddress(page)
        const shown = await getShownDiscount(page)
        assert.ok(shown > 0, 'checkout shows no discount for the link code')

        const order = await getOrder(admin.page, await placeCodOrder(page))
        assert.equal(order.custom_discount_codes, CODE)
        assert.equal(Number(order.custom_code_order_discount), shown)
        assert.equal(Number(order.custom_code_order_discount), Math.round(Number(order.total) * 10) / 100)
      })
    },
    { timeout: 240000 },
  )

  uiTest(
    admin,
    'a cart link with mode=add keeps the cart and adds its code',
    async () => {
      await ensureOrderCode(admin.page)
      const [first, second] = await findStockedItems(admin.page, 2)

      await withGuest(async (page) => {
        await openCartLink(page, [first], { return_to: 'cart' })
        await openCartLink(page, [second], { mode: 'add', discount: CODE })
        const cart = await apiPost(page, 'commera.api.server_cart.get_server_cart')
        assert.deepEqual(cart.lines.map((line) => line.variant.item_code).sort(), [first, second].sort())

        await saveSummerAddress(page)
        assert.ok((await getShownDiscount(page)) > 0, 'the code from the add link was not applied')
      })
    },
    { timeout: 240000 },
  )

  uiTest(
    admin,
    'a code typed into the promo box after checkout opened reaches the checkout',
    async () => {
      // The Summer theme has no promo box; the default theme's checkout does.
      await ensureOrderCode(admin.page)
      await useTheme(admin.page, 'Shop Default Theme')
      const [item] = await findStockedItems(admin.page, 1)
      const email = await createShopper(admin.page, 'promo')

      await withGuest(async (page) => {
        await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2', timeout: 60000 })
        await signIn(page, email)
        await openCartLink(page, [item])
        assert.ok(page.url().includes('/cart/checkout'), `a signed-in cart link landed on ${page.url()}`)

        await clickByText(page, 'button', 'apply promo code')
        // The page holds more than one promo box; only the open one is visible.
        await page.waitForFunction(
          () => [...document.querySelectorAll('input[name="prompt"]')].some((input) => input.offsetParent !== null),
          { timeout: 15000 },
        )
        const input = await page.evaluateHandle(() =>
          [...document.querySelectorAll('input[name="prompt"]')].find((element) => element.offsetParent !== null),
        )
        await input.asElement().type(CODE)
        const applied = page.waitForResponse((response) => response.url().includes('apply_discount_code'), {
          timeout: 30000,
        })
        await clickByText(page, 'button', 'Apply')
        const reply = await applied
        assert.equal(reply.status(), 200, `applying the code failed: ${(await reply.text()).slice(0, 300)}`)
        // The box reloads the page once the code is applied, so wait for the code rather than the reload.
        await page.waitForFunction(
          (code) => document.body.innerText.includes(code) && document.body.innerText.includes('Discount'),
          { timeout: 60000 },
          CODE,
        )
      })

      const [quotation] = await listResource(
        admin.page,
        'Quotation',
        { contact_email: email, docstatus: 0 },
        ['name', 'custom_discount_codes', 'custom_code_order_discount', 'total'],
      )
      assert.ok(quotation, `no checkout Quotation for ${email}`)
      assert.equal(quotation.custom_discount_codes, CODE)
      assert.equal(Number(quotation.custom_code_order_discount), Math.round(Number(quotation.total) * 10) / 100)
    },
    { timeout: 240000 },
  )

  uiTest(
    admin,
    "signing in merges the guest cart into the account's cart",
    async () => {
      await useTheme(admin.page, created.theme || 'Summer Theme')
      const [saved, brought] = await findStockedItems(admin.page, 2)
      const email = await createShopper(admin.page, 'signin')

      // A brand-new account has no server cart, so only an existing one shows whether the guest cart survives.
      await withGuest(async (page) => {
        await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2', timeout: 60000 })
        await signIn(page, email)
        await openCartLink(page, [saved], { return_to: 'cart' })
      })

      await withGuest(async (page) => {
        await openCartLink(page, [brought], { return_to: 'cart' })
        await signIn(page, email)

        await page.goto(`${BASE}/en/cart`, { waitUntil: 'networkidle2', timeout: 60000 })
        const cart = await apiPost(page, 'commera.api.server_cart.get_server_cart')
        assert.ok(cart, 'the signed-in shopper has no server cart')
        assert.deepEqual(
          cart.lines.map((line) => line.variant.item_code).sort(),
          [saved, brought].sort(),
          "the guest's line was not merged into the account's cart",
        )
      })
    },
    { timeout: 240000 },
  )
})
