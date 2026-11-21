import assert from 'node:assert/strict'
import { test } from 'node:test'
import { resultExits } from '../../src/data/importSteps.js'

test('outside onboarding the result offers the products page and the overview', () => {
  assert.deepEqual(
    resultExits(true).map((exit) => exit.path),
    ['/products', '/'],
  )
})

test('inside onboarding the result only closes back to the setup step', () => {
  assert.deepEqual(resultExits(false), [{ label: 'Back to setup' }])
})
