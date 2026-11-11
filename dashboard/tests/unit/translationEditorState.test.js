import assert from 'node:assert/strict'
import { test } from 'node:test'
import { effectScope, nextTick, ref } from 'vue'
import { changePending, savePending, useOpenedTranslation } from '../../src/data/translationEditorState.js'
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
  await state.open('same-name', async () => ({ item: { name: 'same-name', value: 'Arabic' } }))
  const response = deferred()
  const stale = state.open('same-name', () => response.promise)
  language.value = 'fr'
  assert.equal(state.openedItem.value, null)
  await state.open('same-name', async () => ({ item: { name: 'same-name', value: 'French' } }))
  response.resolve({ item: { name: 'same-name', value: 'Arabic' } })
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


test('the change handler keeps a reversion to the pre-save value pending', async () => {
  const response = deferred()
  const pending = {}
  const field = { value: 'A', status: 'current' }
  changePending(pending, 'title', field, 'B')
  const submitted = { ...pending }
  const saving = savePending(pending, () => response.promise)
  changePending(pending, 'title', field, 'A', submitted)
  response.resolve(1)
  await saving
  assert.deepEqual(pending, { title: 'A' })
  changePending(pending, 'title', { ...field, value: 'B' }, 'B')
  assert.deepEqual(pending, {})
})

test('refresh uses one request for multiple saved records and updates their statuses and counts', async () => {
  const scope = effectScope()
  const calls = []
  const oldItems = ['first', 'second'].map((name) => ({ name, to_do: 1, fields: [{ value: '', status: 'missing' }] }))
  const freshItems = oldItems.map((item) => ({ ...item, to_do: 0, fields: [{ value: 'saved', status: 'current' }] }))
  const state = scope.run(() => useTranslationItems(ref('ar'), ref('product'), ref('todo'), async (params) => {
    calls.push(params)
    return { data: params.records ? { items: freshItems } : { items: oldItems, total: 2, to_do: 2 } }
  }))
  await nextTick()
  calls.length = 0
  const fresh = await state.refresh(['first', 'second'])
  assert.equal(calls.length, 1)
  assert.deepEqual(calls[0].records, ['first', 'second'])
  assert.deepEqual(fresh, freshItems)
  assert.deepEqual(state.items.value, freshItems)
  assert.equal(state.toDoCount.value, 0)
  scope.stop()
})

test('a failed detail load exposes an error and can retry without becoming a missing record', async () => {
  const scope = effectScope()
  let succeeds = false
  const list = scope.run(() => useTranslationItems(ref('ar'), ref('product'), ref('todo'), async (params) => {
    if (!params.record) return { data: { items: [] } }
    return succeeds ? { data: { items: [{ name: params.record }] } } : { error: new Error('offline') }
  }))
  const state = scope.run(() => useOpenedTranslation(ref('ar'), ref('product')))
  await nextTick()
  await state.open('linked-record', list.fetchItem)
  assert.equal(state.loadError.value.message, 'offline')
  assert.equal(state.failedName.value, 'linked-record')
  assert.equal(state.unknownName.value, '')
  succeeds = true
  await state.open('linked-record', list.fetchItem)
  assert.equal(state.loadError.value, null)
  assert.equal(state.openedItem.value.name, 'linked-record')
  await state.open('missing', async () => ({ item: null }))
  assert.equal(state.unknownName.value, 'missing')
  assert.equal(state.loadError.value, null)
  scope.stop()
})


test('a failed save retains a field edited back to its submitted value', async () => {
  const response = deferred()
  const pending = { title: 'B' }
  const submitted = { ...pending }
  const saving = savePending(pending, () => response.promise)
  changePending(pending, 'title', { value: 'A', status: 'current' }, 'B', submitted)
  response.resolve(null)
  await saving
  assert.deepEqual(pending, { title: 'B' })
})
