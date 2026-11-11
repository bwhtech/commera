import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { ref } from 'vue'

const vueUrl = import.meta.resolve('vue')
const moduleUrl = (source) => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
const translate = (message) => message
const toast = { success() {}, error() {} }
const autosaveSource = await readFile(new URL('../../src/data/useSettingsAutosave.js', import.meta.url), 'utf8')
const autosaveUrl = moduleUrl(autosaveSource
  .replace("from 'vue'", `from '${vueUrl}'`)
  .replace("import { toast } from 'frappe-ui'", `const toast = { success() {} }`)
  .replace("import { __ } from './translation'", `const __ = (message) => message`))
const { useSettingsAutosave } = await import(autosaveUrl)

function delayedForm() {
  const requests = []
  const save = { submit(params) { return new Promise((resolve, reject) => requests.push({ params, resolve, reject })) } }
  const form = useSettingsAutosave(save, { params: { handle: 'gulf' }, preserveEdits: true })
  form.adopt({ market_name: 'Gulf', countries: ['UAE'], languages: ['ar', 'en'], default_language: 'ar' })
  return { form, requests }
}

const tick = () => new Promise((resolve) => setImmediate(resolve))

test('a delayed country save preserves a name still being typed', async () => {
  const { form, requests } = delayedForm()
  const saving = form.commit('countries', ['UAE', 'Oman'], 'Countries')
  await tick()
  form.set('market_name', 'Gulf States')
  requests[0].resolve({ market_name: 'Gulf', countries: ['UAE', 'Oman'] })
  await saving
  assert.equal(form.values.value.market_name, 'Gulf States')
  assert.deepEqual(form.values.value.countries, ['UAE', 'Oman'])
})

test('a delayed name save preserves later typing in the same field', async () => {
  const { form, requests } = delayedForm()
  const saving = form.commit('market_name', 'Gulf States', 'Name')
  await tick()
  form.set('market_name', 'Gulf States region')
  requests[0].resolve({ market_name: 'Gulf States' })
  await saving
  assert.equal(form.values.value.market_name, 'Gulf States region')
  assert.equal(form.stored.value.market_name, 'Gulf States')
})

test('other settings panels retain merged adoption, rollback, params and reload callbacks', async () => {
  const calls = []
  const form = useSettingsAutosave({ submit: async (params) => {
    calls.push(params)
    if (params.name === 'refused') throw new Error('Refused')
    return { name: 'Server name' }
  } }, { params: { tab: 'general' } })
  form.adopt({ name: 'Original', secret: 'stored' })
  form.adopt({ enabled: 1 })
  await form.commit('name', 'Changed', 'Name')
  assert.equal(form.values.value.name, 'Server name')
  assert.equal(form.values.value.secret, 'stored')
  assert.deepEqual(calls[0], { tab: 'general', name: 'Changed' })
  await form.commit('name', 'refused', 'Name')
  assert.equal(form.values.value.name, 'Server name')
  let reloaded = false
  await form.commit('name', 'Plugin name', 'Name', async () => {
    reloaded = true
    form.adopt({ name: 'Reloaded name' })
  })
  assert.equal(reloaded, true)
  assert.equal(form.values.value.name, 'Reloaded name')
})

test('rapid checkbox changes serialize and preserve queued values including a return to the original', async () => {
  const { form, requests } = delayedForm()
  const first = form.commit('countries', ['UAE', 'Oman'], 'Countries')
  await tick()
  const second = form.commit('countries', ['UAE'], 'Countries')
  assert.equal(requests.length, 1)
  requests[0].resolve({ countries: ['UAE', 'Oman'] })
  await first
  assert.deepEqual(form.values.value.countries, ['UAE'])
  await tick()
  assert.deepEqual(requests[1].params, { handle: 'gulf', countries: ['UAE'] })
  requests[1].resolve({ countries: ['UAE'] })
  await second
  assert.deepEqual(form.stored.value.countries, ['UAE'])
})

test('a failed request preserves newer edits and the queue recovers', async () => {
  const { form, requests } = delayedForm()
  const first = form.commit('market_name', 'Gulf States', 'Name')
  await tick()
  const second = form.commit('market_name', 'Gulf region', 'Name')
  requests[0].reject(new Error('Refused'))
  await first
  assert.equal(form.values.value.market_name, 'Gulf region')
  await tick()
  requests[1].resolve({ market_name: 'Gulf region' })
  await second
  assert.equal(form.stored.value.market_name, 'Gulf region')
})

test('a language save adopts the server default without replacing a queued default', async () => {
  const { form, requests } = delayedForm()
  const first = form.commit('languages', ['en'], 'Languages')
  await tick()
  requests[0].resolve({ languages: ['en'], default_language: 'en' })
  await first
  assert.equal(form.values.value.default_language, 'en')
})

test('a language response preserves a newer queued default language', async () => {
  const { form, requests } = delayedForm()
  const first = form.commit('languages', ['en', 'fr'], 'Languages')
  await tick()
  const second = form.commit('default_language', 'fr', 'Default language')
  requests[0].resolve({ languages: ['en', 'fr'], default_language: 'en' })
  await first
  assert.equal(form.values.value.default_language, 'fr')
  await tick()
  requests[1].resolve({ languages: ['en', 'fr'], default_language: 'fr' })
  await second
  assert.equal(form.stored.value.default_language, 'fr')
})

async function marketForm(store, actions) {
  const source = await readFile(new URL('../../src/data/useMarketForm.js', import.meta.url), 'utf8')
  const imports = {
    vue: `export { computed, ref } from '${vueUrl}'`,
    'frappe-ui': 'export const toast = globalThis.marketFormTest.toast',
    './api': 'export const useAdminAction = (path) => globalThis.marketFormTest.actions[path]; export const wasAborted = () => false',
    './errors': 'export const errorMessage = (error) => error.message',
    './marketUrls': 'export const errorField = (error) => error.field',
    './markets': 'export const marketStore = globalThis.marketFormTest.store',
    './translation': 'export const __ = globalThis.marketFormTest.translate',
  }
  globalThis.marketFormTest = { store, actions, toast, translate }
  let transformed = source.replace("'./useSettingsAutosave'", `'${autosaveUrl}'`)
  for (const [path, stub] of Object.entries(imports)) transformed = transformed.replace(`'${path}'`, `'${moduleUrl(stub)}'`)
  return import(moduleUrl(transformed))
}

test('creating New returns a real new handle that opens the saved record', async () => {
  const records = new Map()
  const store = { choices: ref({}), find: (handle) => records.get(handle), upsert: (record) => records.set(record.handle, record) }
  const actions = {
    'markets.create_market': { submit: async (params) => ({ ...params, handle: 'new' }) },
    'markets.update_market': { submit: async (params) => ({ ...records.get(params.handle), ...params }) },
  }
  const { useMarketForm, NEW_MARKET } = await marketForm(store, actions)
  const draft = useMarketForm(NEW_MARKET)
  draft.set('market_name', 'New')
  draft.set('countries', ['Oman'])
  draft.setLanguages(['en'])
  draft.set('sale_price_list', 'Standard Selling')
  assert.equal(draft.canCreate.value, true)
  const handle = await draft.create()
  assert.equal(handle, 'new')
  const editor = useMarketForm(handle)
  assert.equal(editor.isNew, false)
  assert.equal(editor.values.value.market_name, 'New')
  await editor.change('market_name', 'New region', 'Name')
  assert.equal(records.get('new').market_name, 'New region')
  for (const field of ['sale_price_list', 'compare_at_price_list', 'countries', 'languages']) {
    actions['markets.update_market'].submit = async () => ({ field, message: 'Invalid value' })
    await editor.change(field, 'invalid', field)
    assert.deepEqual(editor.errors.value, { [field]: 'Invalid value' })
    assert.notEqual(records.get('new')[field], 'invalid')
  }
})
