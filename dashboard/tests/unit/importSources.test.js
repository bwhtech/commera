import assert from 'node:assert/strict'
import { test } from 'node:test'
import { SOURCE_STEPS, sourceCards } from '../../src/data/importSteps.js'

test('every source card leads into an import that exists', () => {
  for (const hasErpnextItems of [false, true]) {
    for (const card of sourceCards(hasErpnextItems)) assert.ok(SOURCE_STEPS[card.value], card.value)
  }
})

test('the spreadsheet comes first and ERPNext second, only when it has items to import', () => {
  assert.deepEqual(
    sourceCards(false).map((card) => card.value),
    ['csv'],
  )
  assert.deepEqual(
    sourceCards(true).map((card) => card.value),
    ['csv', 'erpnext'],
  )
})
