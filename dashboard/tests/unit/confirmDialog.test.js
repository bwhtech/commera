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
