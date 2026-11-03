import assert from 'node:assert/strict'
import { test } from 'node:test'
import { SETUP_STEPS, countStepsDone, stepsFromState } from '../../src/data/firstRun.js'

test('stepsFromState ticks exactly the steps the server reports done', () => {
  const steps = stepsFromState({ product: true, payments: false, shipping: true, theme: false })
  assert.deepEqual(
    steps.map((step) => [step.key, step.done]),
    [['product', true], ['payments', false], ['shipping', true], ['theme', false]],
  )
  assert.equal(steps.length, SETUP_STEPS.length)
})

test('stepsFromState reads a missing or non-boolean answer as not done', () => {
  assert.ok(stepsFromState(null).every((step) => !step.done))
  assert.ok(stepsFromState({ product: 1, payments: 'yes' }).every((step) => !step.done))
})

test('countStepsDone is steps_done, 0 to 4', () => {
  assert.equal(countStepsDone(undefined), 0)
  assert.equal(countStepsDone({ product: true }), 1)
  assert.equal(countStepsDone({ product: true, payments: true, shipping: true, theme: true }), 4)
  assert.equal(countStepsDone({ product: true, unknown: true }), 1)
})
