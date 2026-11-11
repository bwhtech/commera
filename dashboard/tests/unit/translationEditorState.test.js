import assert from 'node:assert/strict'
import { test } from 'node:test'
import { effectScope, nextTick, ref } from 'vue'
import { savePending, useOpenedTranslation } from '../../src/data/translationEditorState.js'
import { useTranslationItems } from '../../src/data/translationItems.js'

function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

test('edits during a deferred save remain pending', async () => {
  const response = deferred()
  const pending = { title: 'submitted', content: 'submitted' }
  const saving = savePending(pending, () => response.promise)
  pending.title = 'typed while saving'
  pending.newField = 'new'
  response.resolve(2)
  await saving
  assert.deepEqual(pending, { title: 'typed while saving', newField: 'new' })
})

test('opened records reset across languages and resources and ignore stale responses', async () => {
  const scope = effectScope()
  const language = ref('ar')
  const resource = ref('product')
  const state = scope.run(() => useOpenedTranslation(language, resource))
  await state.open('same-name', async () => ({ name: 'same-name', value: 'Arabic' }))
  const response = deferred()
  const stale = state.open('same-name', () => response.promise)
  language.value = 'fr'
  assert.equal(state.openedItem.value, null)
  await state.open('same-name', async () => ({ name: 'same-name', value: 'French' }))
  response.resolve({ name: 'same-name', value: 'Arabic' })
  await stale
  assert.equal(state.openedItem.value.value, 'French')
  resource.value = 'collection'
  assert.equal(state.openedItem.value, null)
  scope.stop()
})

test('failed lists remain unsuccessful until retry succeeds', async () => {
  const scope = effectScope()
  let succeeds = false
  const state = scope.run(() => useTranslationItems(ref('ar'), ref('product'), ref('todo'), async () =>
    succeeds ? { data: { items: [], total: 0, to_do: 0 } } : { error: new Error('offline') },
  ))
  await nextTick()
  assert.equal(state.loaded.value, false)
  assert.equal(state.loadError.value.message, 'offline')
  succeeds = true
  await state.load()
  assert.equal(state.loaded.value, true)
  assert.equal(state.loadError.value, undefined)
  scope.stop()
})

test('old list and record responses cannot replace the new language', async () => {
  const scope = effectScope()
  const language = ref('ar')
  const arabicList = deferred()
  const arabicRecord = deferred()
  const state = scope.run(() => useTranslationItems(language, ref('product'), ref('todo'), async (params) => {
    if (params.language === 'ar') return params.record ? arabicRecord.promise : arabicList.promise
    return { data: { items: [{ name: 'same-name', value: 'French' }], total: 1, to_do: 1 } }
  }))
  const stale = state.fetchItem('same-name')
  language.value = 'fr'
  await nextTick()
  arabicList.resolve({ data: { items: [{ name: 'same-name', value: 'Arabic' }] } })
  arabicRecord.resolve({ data: { items: [{ name: 'same-name', value: 'Arabic' }] } })
  assert.equal(await stale, null)
  await nextTick()
  assert.equal(state.items.value[0].value, 'French')
  scope.stop()
})
