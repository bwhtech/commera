import assert from 'node:assert/strict'
import { test } from 'node:test'
import { effectScope, nextTick, ref } from 'vue'
import { useDialogLayer } from '../../src/utils/dialogLayers.js'

function layer(open) {
  const isOpen = ref(open)
  const scope = effectScope()
  const isCovered = scope.run(() => useDialogLayer(isOpen))
  return { isOpen, isCovered, dispose: () => scope.stop() }
}

test('a dialog opened over another covers it until it closes', async () => {
  const form = layer(true)
  const confirm = layer(false)
  assert.equal(form.isCovered.value, false)

  confirm.isOpen.value = true
  await nextTick()
  assert.equal(form.isCovered.value, true)
  assert.equal(confirm.isCovered.value, false)

  confirm.isOpen.value = false
  await nextTick()
  assert.equal(form.isCovered.value, false)
  form.dispose()
  confirm.dispose()
})

test('three layers: only the top one is uncovered, and an unmounted one stops covering', async () => {
  const form = layer(true)
  const collection = layer(true)
  const confirm = layer(true)
  assert.deepEqual([form, collection, confirm].map((each) => each.isCovered.value), [true, true, false])

  confirm.dispose()
  assert.deepEqual([form, collection].map((each) => each.isCovered.value), [true, false])
  collection.dispose()
  form.dispose()
})
