import assert from 'node:assert/strict'
import { test } from 'node:test'
import { effectScope, nextTick, ref } from 'vue'
import { changePending, useTranslationSave, useOpenedTranslation } from '../../src/data/translationEditorState.js'
import { useTranslationItems } from '../../src/data/translationItems.js'

function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

test('a deferred save locks until refresh adopts saved values', async () => {
  const response = deferred()
  const refreshed = deferred()
  const pending = { title: 'B' }
  const state = useTranslationSave(pending, ref('ar/product'))
  let stored = 'A'
  const saving = state.save(() => response.promise, async () => {
    await refreshed.promise
    stored = 'B'
  })
  assert.equal(state.saving.value, true)
  assert.equal(pending.title ?? stored, 'B')
  await state.save(() => assert.fail('duplicate save'), () => {})
  response.resolve(1)
  await nextTick()
  assert.equal(state.saving.value, true)
  assert.equal(pending.title ?? stored, 'B')
  refreshed.resolve()
  await saving
  assert.equal(state.saving.value, false)
  assert.deepEqual(pending, {})
  assert.equal(pending.title ?? stored, 'B')
})

test('failed saves retain every edit and unlock for retry', async () => {
  for (const fails of [false, true]) {
    const pending = { title: 'B', content: 'draft' }
    const state = useTranslationSave(pending, ref('ar/product'))
    const attempt = state.save(async () => {
      if (fails) throw new Error('offline')
      return null
    }, () => assert.fail('refresh on failed save'))
    if (fails) await assert.rejects(attempt, /offline/)
    else await attempt
    assert.deepEqual(pending, { title: 'B', content: 'draft' })
    assert.equal(state.saving.value, false)
  }
})

test('save completion cannot refresh or clear a different context', async () => {
  const response = deferred()
  const context = ref('ar/product')
  const pending = { arabic: 'B' }
  const state = useTranslationSave(pending, context)
  const saving = state.save(() => response.promise, () => assert.fail('stale refresh'))
  context.value = 'fr/product'
  delete pending.arabic
  pending.french = 'French'
  response.resolve(1)
  await saving
  assert.deepEqual(pending, { french: 'French' })
})

test('drafts remain visible if the saved record cannot refresh', async () => {
  const pending = { title: 'B' }
  const state = useTranslationSave(pending, ref('ar/product'))
  await state.save(async () => 1, async () => false)
  assert.deepEqual(pending, { title: 'B' })
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


test('reverting an idle edit clears it, except confirmation of outdated text', () => {
  const pending = {}
  const field = { value: 'A', status: 'current' }
  changePending(pending, 'title', field, 'B')
  assert.deepEqual(pending, { title: 'B' })
  changePending(pending, 'title', field, 'A')
  assert.deepEqual(pending, {})
  changePending(pending, 'title', { ...field, status: 'outdated' }, 'A')
  assert.deepEqual(pending, { title: 'A' })
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
