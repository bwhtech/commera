import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  PREVIEW_MAX_AGE_MS,
  buildHomeTasks,
  describeDomains,
  describeStoreStatus,
  listBlockers,
  needsPreviewCapture,
  storeSlug,
} from '../../src/data/home.js'

const home = (fields) => ({
  cod_enabled: false,
  tasks: { products: false, payments: false, shipping: false, brand: false },
  ...fields,
})
const keys = (tasks) => tasks.map((task) => task.key)
const find = (tasks, key) => tasks.find((task) => task.key === key)

test('the cards run products, payments, shipping, brand, then domain', () => {
  const tasks = buildHomeTasks(home(), { status: 'none', name: null }, 'shop.frappe.cloud')
  assert.deepEqual(keys(tasks), ['products', 'payments', 'shipping', 'brand', 'domain'])
})

test('off Frappe Cloud there is no domain card', () => {
  assert.deepEqual(keys(buildHomeTasks(home(), null, 'shop.example')), ['products', 'payments', 'shipping', 'brand'])
})

test('cash on delivery makes online payments optional', () => {
  const withCod = find(buildHomeTasks(home({ cod_enabled: true }), null, 'shop.example'), 'payments')
  assert.equal(withCod.title, 'Take online payments')
  assert.equal(withCod.required, false)

  const withoutCod = find(buildHomeTasks(home(), null, 'shop.example'), 'payments')
  assert.equal(withoutCod.title, 'Set up payments')
  assert.equal(withoutCod.required, true)
})

test('a task is done when the server says so', () => {
  const tasks = buildHomeTasks(home({ tasks: { products: true, payments: false, shipping: true, brand: false } }), null, 'x')
  assert.deepEqual(tasks.filter((task) => task.done).map((task) => task.key), ['products', 'shipping'])
})

test('the domain card names the site address, then the domain being set up', () => {
  const none = find(buildHomeTasks(home(), { status: 'none', name: null }, 'shop.frappe.cloud'), 'domain')
  assert.match(none.description, /shop\.frappe\.cloud/)
  assert.equal(none.done, false)

  const pending = find(buildHomeTasks(home(), { status: 'pending', name: 'shop.com' }, 'shop.frappe.cloud'), 'domain')
  assert.equal(pending.title, 'Finishing your domain')
  assert.match(pending.description, /shop\.com/)

  const connected = find(buildHomeTasks(home(), { status: 'connected', name: 'shop.com' }, 'shop.frappe.cloud'), 'domain')
  assert.equal(connected.done, true)
})

test('a custom domain is connected only once it is primary and has a certificate', () => {
  const site = { domain: 'shop.frappe.cloud', is_primary: false, is_default: true, tls: true }
  const custom = (fields) => ({ domain: 'shop.com', is_primary: false, is_default: false, tls: false, ...fields })

  assert.equal(describeDomains(null), null)
  assert.deepEqual(describeDomains({ domains: [{ ...site, is_primary: true }] }), { status: 'none', name: null })
  assert.deepEqual(describeDomains({ domains: [site, custom()] }), { status: 'pending', name: 'shop.com' })
  assert.deepEqual(describeDomains({ domains: [site, custom({ is_primary: true })] }), { status: 'pending', name: 'shop.com' })
  assert.deepEqual(describeDomains({ domains: [site, custom({ is_primary: true, tls: true })] }), {
    status: 'connected',
    name: 'shop.com',
  })
})

// Frappe's `creation` shape, in local time, which is how the browser reads a bare timestamp.
const siteTimestamp = (date) => {
  const pad = (number) => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

test('the preview is captured when missing or a day old, and only by someone who can', () => {
  const now = new Date('2026-11-04T12:00:00').getTime()
  const at = (ms) => siteTimestamp(new Date(now - ms))

  assert.equal(needsPreviewCapture(null, now), false)
  assert.equal(needsPreviewCapture({ can_capture: false, image: null }, now), false)
  assert.equal(needsPreviewCapture({ can_capture: true, image: null, captured_on: null }, now), true)
  assert.equal(needsPreviewCapture({ can_capture: true, image: '/files/a.webp', captured_on: at(60_000) }, now), false)
  assert.equal(needsPreviewCapture({ can_capture: true, image: '/files/a.webp', captured_on: at(PREVIEW_MAX_AGE_MS + 60_000) }, now), true)
})

test('the publish warning names the blocking tasks as a sentence list', () => {
  const blockers = buildHomeTasks(home(), null, 'x').filter((task) => task.required)
  assert.equal(listBlockers(blockers), 'products, payments, and shipping')
  assert.equal(listBlockers(blockers.slice(1)), 'payments and shipping')
})

test('the slug keeps letters and digits, and falls back when there is no name', () => {
  assert.equal(storeSlug('Indigo Loom & Co.'), 'indigoloomco')
  assert.equal(storeSlug(''), 'yourstore')
  assert.equal(storeSlug(null), 'yourstore')
})

test('the hero copy follows the store from blocked, to ready, to live', () => {
  assert.equal(describeStoreStatus(false, 2).label, '2 steps before you can sell')
  assert.equal(describeStoreStatus(false, 1).label, '1 step before you can sell')
  assert.equal(describeStoreStatus(false, 0).label, 'Ready to publish')
  assert.equal(describeStoreStatus(false, 0).headline, 'Your store is taking shape')
  assert.equal(describeStoreStatus(true, 2).headline, 'Your store is open for business')
})
