import assert from 'node:assert/strict'
import { test } from 'node:test'
import { errorMessage, isStaleWrite } from '../../src/data/errors.js'

test('a save refused over a page that changed elsewhere reads as stale', () => {
  const refusal = new Error('TimestampMismatchError: This page changed elsewhere. Reload to continue.')
  assert.equal(isStaleWrite(Object.assign(refusal, { type: 'TimestampMismatchError' })), true)
  assert.equal(isStaleWrite(new Error('TimestampMismatchError: This page changed elsewhere.')), true)
  assert.equal(errorMessage(refusal), 'This page changed elsewhere. Reload to continue.')
})

test('other refusals and no error are not stale', () => {
  assert.equal(isStaleWrite(Object.assign(new Error('ValidationError: Bad layout'), { type: 'ValidationError' })), false)
  assert.equal(isStaleWrite(null), false)
  assert.equal(isStaleWrite(undefined), false)
})
