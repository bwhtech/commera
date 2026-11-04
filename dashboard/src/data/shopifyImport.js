// The Shopify import screen's server state: the connection, the mapping options, and the run
// being watched. Runs happen in a background job, so the screen polls the run it shows.
import { reactive } from 'vue'
import { createAdminCaller } from './adminCaller'

const { attempt, call } = createAdminCaller('shopify_import.')

// Keys are the server's resource names (commera.shopify.importers.IMPORTERS), in import order.
export const RESOURCE_HINTS = {
  Store: 'Store name, contact details and currency',
  Collections: 'Collections, with the products in them',
  Products: 'Variants, prices, images, stock and SEO',
  Pages: 'Online store pages',
  Customers: 'Customers, contacts and addresses. No emails are sent',
  Redirects: 'Your own Shopify URL redirects',
}

// Scan counts are keyed by these names in commera.shopify.queries.COUNT_QUERIES.
export const COUNT_FOR_RESOURCE = {
  Collections: 'Collections',
  Products: 'Products',
  Pages: 'Pages',
  Customers: 'Customers',
  Redirects: 'Redirects',
}

export const STATUS_THEMES = {
  Pending: 'gray',
  Queued: 'gray',
  Running: 'blue',
  Completed: 'green',
  'Completed With Errors': 'orange',
  Failed: 'red',
}

export const isActive = (run) => Boolean(run) && ['Queued', 'Running'].includes(run.status)

export const shopify = reactive({ overview: null, run: null, loadError: null })

export async function loadOverview() {
  const { data, error } = await attempt('get_shopify_import')
  shopify.loadError = error
  if (data) shopify.overview = data
  return data
}

export async function loadRun(name) {
  const data = await call('get_run', { name })
  if (data) shopify.run = data
  return data
}

// Resolves to the new overview, or null when Shopify or the server refused the connection.
export async function saveConnection(fields) {
  const data = await call('save_connection', fields)
  if (data) shopify.overview = data
  return data
}

export async function disconnect() {
  const data = await call('disconnect')
  if (data) shopify.overview = data
  return data
}

export async function saveOption(fieldname, value) {
  const options = await call('save_option', { fieldname, value })
  if (options) shopify.overview.options = options
  return options
}

async function startRun(method, params = {}) {
  const started = await call(method, params)
  if (!started) return null
  await Promise.all([loadOverview(), loadRun(started.name)])
  return started
}

export const startScan = () => startRun('start_scan')

export const startImport = (resources, onlyChanged) =>
  startRun('start_import', { resources, only_changed: onlyChanged ? 1 : 0 })
