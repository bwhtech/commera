import assert from 'node:assert/strict'
import { test } from 'node:test'
import { BUSY_PHASES, canMove, isBusy, nextPhase } from '../../src/data/importPhase.js'

test('no step change while a request is in flight', () => {
  for (const phase of BUSY_PHASES) {
    assert.equal(isBusy(phase), true, phase)
    assert.equal(canMove(phase), false, phase)
  }
  assert.equal(canMove('idle'), true)
})

test('a landed import is terminal and a refused one may be retried', () => {
  assert.equal(canMove('done'), false)
  assert.equal(nextPhase('done', 'running'), null)
  assert.equal(canMove('failed'), true)
  assert.equal(nextPhase('failed', 'running'), 'running')
})

test('a second start while one is running is refused', () => {
  assert.equal(nextPhase('running', 'running'), null)
  assert.equal(nextPhase('parsing', 'parsing'), null)
  assert.equal(nextPhase('uploading', 'matching'), null)
  assert.equal(nextPhase('idle', 'parsing'), 'parsing')
})
