import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const moduleUrl = (source) => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`

test('loads asked for while one is in flight share it instead of aborting it', async () => {
  const source = await readFile(new URL('../../src/data/collections.js', import.meta.url), 'utf8')
  const pending = []
  globalThis.collectionsTest = {
    read: { data: null, error: null, fetch: () => new Promise((resolve) => pending.push(resolve)) },
  }
  const imports = {
    vue: `export { computed } from '${import.meta.resolve('vue')}'`,
    'frappe-ui': 'export const dialog = {}; export const toast = {}',
    './api': 'export const useAdminRead = () => globalThis.collectionsTest.read; export const useAdminAction = () => ({}); export const trySubmit = () => true',
    './translation': 'export const __ = (message) => message',
  }
  let transformed = source
  for (const [path, stub] of Object.entries(imports)) transformed = transformed.replace(`'${path}'`, `'${moduleUrl(stub)}'`)
  const { loadCollections } = await import(moduleUrl(transformed))

  const first = loadCollections()
  assert.equal(loadCollections(), first)
  assert.equal(pending.length, 1)

  pending[0]()
  await first
  loadCollections()
  assert.equal(pending.length, 2)
})
