import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createdProducts } from '../../src/data/importPhase.js'

const csvRun = (phase, created) => ({ source: 'csv', phase, created, erpnext: { status: null } })
const erpnextRun = (status) => ({ source: 'erpnext', phase: 'done', created: [], erpnext: { status } })

test('a landed spreadsheet import that made products changes the list', () => {
  assert.equal(createdProducts(csvRun('done', [{ item_template: 'CAP' }])), true)
})

test('a spreadsheet import that made nothing, failed or never ran leaves the list alone', () => {
  assert.equal(createdProducts(csvRun('done', [])), false)
  assert.equal(createdProducts(csvRun('failed', [])), false)
  assert.equal(createdProducts(csvRun('idle', [])), false)
})

test('an ERPNext import changes the list once it has created a product, even if some items failed', () => {
  assert.equal(createdProducts(erpnextRun({ status: 'failed', created: 2 })), true)
  assert.equal(createdProducts(erpnextRun({ status: 'done', created: 0 })), false)
  assert.equal(createdProducts(erpnextRun(null)), false)
})
