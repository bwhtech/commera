import assert from 'node:assert/strict'
import { test } from 'node:test'
import { askConfirm, confirmState, settleConfirm } from '../../src/utils/confirmDialog.js'

const question = { title: 'Discard changes?', message: 'Not saved.', confirmLabel: 'Discard', cancelLabel: 'Keep editing' }

test('the answer resolves the question once and closes the dialog', async () => {
  const answer = askConfirm(question)
  assert.equal(confirmState.open, true)
  settleConfirm(true)
  settleConfirm(false)
  assert.equal(await answer, true)
  assert.equal(confirmState.open, false)
})

test('a new question answers the open one "no", so no caller waits forever', async () => {
  const first = askConfirm(question)
  const second = askConfirm({ ...question, title: 'Leave?' })
  assert.equal(await first, false)
  assert.equal(confirmState.title, 'Leave?')
  settleConfirm(true)
  assert.equal(await second, true)
})

test('a prompt is dirty only while its value differs from the one it opened with', async () => {
  const { askValue, isPromptDirty, promptState } = await import('../../src/utils/confirmDialog.js')
  askValue({ title: 'Low-stock level', label: 'Level', type: 'number', value: 5, confirmLabel: 'Save', submit: async () => true })
  assert.equal(isPromptDirty(), false)
  promptState.value = '99'
  assert.equal(isPromptDirty(), true)
  promptState.value = '5'
  assert.equal(isPromptDirty(), false)
})
