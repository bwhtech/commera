import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const moduleUrl = (source) => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`

test('a refused list toggle keeps the record and reports the refusal without success', async () => {
  const source = await readFile(new URL('../../src/data/markets.js', import.meta.url), 'utf8')
  const errors = []
  const successes = []
  globalThis.marketStoreTest = {
    toast: { error: (message) => errors.push(message), success: (message) => successes.push(message) },
    actions: { call: async () => ({ field: 'enabled', message: 'Market cannot be disabled' }) },
  }
  const imports = {
    vue: `export { computed, ref } from '${import.meta.resolve('vue')}'`,
    'frappe-ui': 'export const toast = globalThis.marketStoreTest.toast',
    './adminCaller': 'export const createAdminCaller = () => globalThis.marketStoreTest.actions',
    './api': 'export const wasAborted = () => false',
    './errors': 'export const errorMessage = (error) => error.message',
    './marketUrls': 'export const countryOwners = () => new Map(); export const marketUrls = () => []',
    './translation': 'export const __ = (message) => message',
  }
  let transformed = source
  for (const [path, stub] of Object.entries(imports)) transformed = transformed.replace(`'${path}'`, `'${moduleUrl(stub)}'`)
  const { marketStore } = await import(moduleUrl(transformed))
  const market = { handle: 'gulf', market_name: 'Gulf', enabled: 1, languages: ['en'] }
  marketStore.upsert(market)
  await marketStore.setEnabled(market, false)
  assert.deepEqual(marketStore.markets.value, [market])
  assert.equal(marketStore.find('gulf').enabled, 1)
  assert.deepEqual(errors, ['Market cannot be disabled'])
  assert.deepEqual(successes, [])
})
