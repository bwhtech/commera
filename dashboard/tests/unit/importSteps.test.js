import assert from 'node:assert/strict'
import { test } from 'node:test'
import { SOURCE_STEPS, stepIndex, stepsFor } from '../../src/data/importSteps.js'

const keys = (source) => stepsFor(source).map((step) => step.key)

test('the spreadsheet keeps its six steps in order', () => {
  assert.deepEqual(keys('csv'), ['source', 'upload', 'map', 'images', 'review', 'run'])
})

test('erpnext picks items and runs, with no upload or mapping', () => {
  assert.deepEqual(keys('erpnext'), ['source', 'pick', 'run'])
})

test('every source starts at the source step, so switching source never strands the step index', () => {
  for (const source of Object.keys(SOURCE_STEPS)) assert.equal(stepIndex(source, 'source'), 0, source)
})

test('steps are found by key per source', () => {
  assert.equal(stepIndex('csv', 'review'), 4)
  assert.equal(stepIndex('erpnext', 'pick'), 1)
  assert.equal(stepIndex('erpnext', 'run'), 2)
  assert.equal(stepIndex('erpnext', 'review'), -1)
})

test('an unknown source falls back to the spreadsheet', () => {
  assert.deepEqual(keys('shopify'), keys('csv'))
})

test('with the spreadsheet as the only source, the flow opens on Upload', () => {
  assert.deepEqual(stepsFor('csv', false).map((step) => step.key), ['upload', 'map', 'images', 'review', 'run'])
  assert.equal(stepIndex('csv', 'review', false), 3)
})
