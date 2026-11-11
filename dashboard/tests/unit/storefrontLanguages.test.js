import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createLanguageSettingsStore } from '../../src/data/languageSettingsStore.js'

function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

function storeWith(attempt, call = async () => null) {
  return createLanguageSettingsStore({ attempt, call, wasAborted: () => false, onAdopt: () => {} })
}

test('opening Languages again fetches changes from another session', async () => {
  let data = { languages: [{ code: 'en' }] }
  const store = storeWith(async () => ({ data }))
  await store.load()
  data = { languages: [{ code: 'en' }, { code: 'ar' }] }
  await store.load()
  assert.equal(store.languages.value.length, 2)
})

test('an older read cannot overwrite a mutation or start during a queued write', async () => {
  const read = deferred()
  const write = deferred()
  let reads = 0
  const store = storeWith(() => { reads += 1; return read.promise }, () => write.promise)
  const loading = store.load()
  const saving = store.mutate('add_storefront_language')
  await store.load()
  assert.equal(reads, 1)
  write.resolve({ languages: [{ code: 'en' }, { code: 'ar' }] })
  await saving
  read.resolve({ data: { languages: [{ code: 'en' }] } })
  await loading
  assert.equal(store.languages.value.length, 2)
})
