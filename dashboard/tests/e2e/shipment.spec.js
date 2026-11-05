import assert from 'node:assert/strict'
import { describe } from 'node:test'
import {
  BASE,
  PREFIX,
  apiPost,
  findByText,
  goto,
  listResource,
  onCleanup,
  realProblems,
  uiTest,
  useSession,
  wait,
} from './harness.js'

const SHIPMENT_METHOD = '/api/method/commera.shipping.shipment.'

async function insert(page, doc) {
  return apiPost(page, 'frappe.client.insert', { doc })
}

async function call(page, method, body) {
  return apiPost(page, method, body)
}

async function makeAddress(page, title, linkDoctype, linkName) {
  const address = await insert(page, {
    doctype: 'Address',
    address_title: `${PREFIX} ${title}`,
    address_type: linkDoctype === 'Company' ? 'Office' : 'Shipping',
    address_line1: '1 Test Street',
    city: 'Mumbai',
    state: 'Maharashtra',
    pincode: '400001',
    country: 'India',
    is_your_company_address: linkDoctype === 'Company' ? 1 : 0,
    links: [{ link_doctype: linkDoctype, link_name: linkName }],
  })
  return address.name
}

async function makeFixtures(session) {
  const { page } = session
  const [company] = await listResource(page, 'Company')
  const [customer] = await listResource(page, 'Customer')
  const [profile] = await listResource(page, 'Shipping Provider Profile', {
    enabled: 1,
  })
  assert.ok(
    company && customer && profile,
    'the site needs a company, a customer and an enabled shipping provider profile',
  )

  const pickupAddress = await makeAddress(page, 'Pickup', 'Company', company.name)
  const deliveryAddress = await makeAddress(page, 'Delivery', 'Customer', customer.name)
  const contact = await insert(page, {
    doctype: 'Contact',
    first_name: PREFIX,
    links: [{ link_doctype: 'Customer', link_name: customer.name }],
  })

  const base = {
    doctype: 'Shipment',
    pickup_from_type: 'Company',
    pickup_company: company.name,
    pickup_address_name: pickupAddress,
    pickup_contact_person: 'Administrator',
    delivery_to_type: 'Customer',
    delivery_customer: customer.name,
    delivery_address_name: deliveryAddress,
    delivery_contact_name: contact.name,
    pickup_date: new Date().toISOString().slice(0, 10),
    pickup_from: '09:00:00',
    pickup_to: '17:00:00',
    value_of_goods: 500,
    shipment_parcel: [{ length: 10, width: 10, height: 10, weight: 1, count: 1 }],
    custom_shipping_provider: profile.name,
  }
  const draft = await insert(page, {
    ...base,
    description_of_content: `${PREFIX} draft`,
  })
  const booked = await insert(page, {
    ...base,
    docstatus: 1,
    description_of_content: `${PREFIX} booked`,
    awb_number: `${PREFIX}-AWB`,
    custom_order_ref: `${PREFIX}-ORDER`,
    custom_shipment_status: 'Ready To Ship',
  })

  onCleanup(session, async () => {
    await goto(page, '/')
    await call(page, 'frappe.client.set_value', {
      doctype: 'Shipment',
      name: booked.name,
      fieldname: 'custom_shipment_status',
      value: 'Delivered',
    })
    await call(page, 'frappe.client.cancel', {
      doctype: 'Shipment',
      name: booked.name,
    })
    for (const [doctype, name] of [
      ['Shipment', booked.name],
      ['Shipment', draft.name],
      ['Contact', contact.name],
      ['Address', deliveryAddress],
      ['Address', pickupAddress],
    ]) {
      await call(page, 'frappe.client.delete', { doctype, name })
    }
  })
  return { draft: draft.name, booked: booked.name }
}

async function openForm(page, name) {
  await page.goto(`${BASE}/desk/shipment/${encodeURIComponent(name)}`, {
    waitUntil: 'networkidle2',
    timeout: 60000,
  })
  await page.waitForFunction((docname) => window.cur_frm?.doc?.name === docname, { timeout: 30000 }, name)
  await wait(800)
}

async function buttonLabels(page) {
  return page.$$eval('.page-actions .inner-group-button, .page-actions button, .custom-actions button', (nodes) =>
    nodes.filter((node) => node.offsetParent !== null).map((node) => node.innerText.trim()),
  )
}

async function dialogText(page) {
  await page.waitForSelector('.modal.show .modal-content', {
    visible: true,
    timeout: 20000,
  })
  return page.$eval('.modal.show .modal-content', (node) => node.innerText)
}

async function closeDialog(page) {
  await page.keyboard.press('Escape')
  await page
    .waitForFunction(() => !document.querySelector('.modal.show'), {
      timeout: 10000,
    })
    .catch(() => {})
}

function pageErrors(problems) {
  return realProblems(problems).filter((entry) => entry.startsWith('PAGEERROR'))
}

describe('shipment form', () => {
  const session = useSession()
  let shipments

  uiTest(session, 'creates the test shipments', async () => {
    await goto(session.page, '/')
    shipments = await makeFixtures(session)
  })

  uiTest(session, 'an unbooked shipment offers Buy Label and nothing that needs a label', async () => {
    await openForm(session.page, shipments.draft)

    const labels = await buttonLabels(session.page)
    assert.ok(labels.includes('Buy Label'), `no Buy Label button; saw ${labels.join(', ')}`)
    for (const label of ['Sync Status', 'Generate Manifest', 'Cancel With Carrier']) {
      assert.ok(!labels.includes(label), `${label} shows before the shipment is booked`)
    }
    assert.deepEqual(pageErrors(session.problems), [], 'the draft form threw in the browser')
  })

  uiTest(session, 'Generate Manifest reaches the server and explains why it cannot run', async () => {
    const { page } = session
    await openForm(page, shipments.booked)

    const labels = await buttonLabels(page)
    for (const label of ['Sync Status', 'Schedule Pickup', 'Generate Manifest', 'Cancel With Carrier']) {
      assert.ok(labels.includes(label), `no ${label} button on a booked shipment; saw ${labels.join(', ')}`)
    }

    const [response] = await Promise.all([
      page.waitForResponse((reply) => reply.url().includes(SHIPMENT_METHOD + 'generate_manifest'), { timeout: 20000 }),
      (await findByText(page, 'button', 'Generate Manifest')).click(),
    ])
    assert.equal(response.status(), 417, 'generate_manifest did not answer with a validation error')
    const message = await dialogText(page)
    assert.ok(
      /Book this shipment before generating a manifest|cannot generate manifests/.test(message),
      `unexpected manifest message: ${message}`,
    )
    await closeDialog(page)
  })

  uiTest(session, 'a plain Cancel on a booked shipment points to Cancel With Carrier', async () => {
    const { page } = session
    await openForm(page, shipments.booked)

    await (await findByText(page, '.page-actions button', 'Cancel')).click()
    await dialogText(page)
    await (await findByText(page, '.modal.show button', 'Yes')).click()
    await page.waitForFunction(
      () =>
        Array.from(document.querySelectorAll('.modal.show')).some((node) =>
          node.innerText.includes('Booked With Carrier'),
        ),
      { timeout: 20000 },
    )
    await closeDialog(page)

    await goto(page, '/')
    const [shipment] = await listResource(page, 'Shipment', { name: shipments.booked }, ['docstatus'])
    assert.equal(shipment.docstatus, 1, 'the booked shipment was cancelled without the carrier')
  })
})
