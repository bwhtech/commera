import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  isRunSettled,
  itemCodesToImport,
  preselectedCodes,
  runPercent,
  toggledSelection,
  selectedAfter,
  selectionOnPage,
} from '../../src/data/erpnextImportState.js'

const page = [
  { item_code: 'SHIRT', preselected: true },
  { item_code: 'MUG', preselected: false },
  { item_code: 'CAP', preselected: true },
]

test('only the items the server preselects start ticked', () => {
  assert.deepEqual(preselectedCodes(page), ['SHIRT', 'CAP'])
  assert.deepEqual(preselectedCodes([]), [])
})

test('the list shows the ticks that fall on its page', () => {
  assert.deepEqual(selectionOnPage(page, ['CAP', 'OTHER-PAGE']), ['CAP'])
})

test('changing ticks on one page keeps the ticks on other pages', () => {
  assert.deepEqual(selectedAfter(page, ['MUG'], ['SHIRT', 'CAP', 'OTHER-PAGE']), ['OTHER-PAGE', 'MUG'])
  assert.deepEqual(selectedAfter(page, [], ['SHIRT']), [])
})

test('everything ticked imports every item, anything less sends the codes', () => {
  assert.equal(itemCodesToImport(['SHIRT', 'MUG', 'CAP'], 3), null)
  assert.deepEqual(itemCodesToImport(['SHIRT', 'CAP'], 3), ['SHIRT', 'CAP'])
})

test('only done and failed end the poll', () => {
  assert.equal(isRunSettled('queued'), false)
  assert.equal(isRunSettled('running'), false)
  assert.equal(isRunSettled('done'), true)
  assert.equal(isRunSettled('failed'), true)
})

test('progress is a whole percent and never divides by zero', () => {
  assert.equal(runPercent(null), 0)
  assert.equal(runPercent({ done: 0, total: 0 }), 0)
  assert.equal(runPercent({ done: 1, total: 3 }), 33)
  assert.equal(runPercent({ done: 5, total: 3 }), 100)
})

test('select all while searching picks only the items shown', () => {
  const allCodes = ['LAMP', 'MUG', 'VASE']
  const selected = toggledSelection({ selected: [], allCodes, shownCodes: ['MUG'], isSearching: true })
  assert.deepEqual(selected, ['MUG'])
  assert.deepEqual(itemCodesToImport(selected, allCodes.length), ['MUG'])
})

test('clearing while searching keeps items picked outside the search', () => {
  const selected = toggledSelection({ selected: ['LAMP', 'MUG'], allCodes: ['LAMP', 'MUG', 'VASE'], shownCodes: ['MUG'], isSearching: true })
  assert.deepEqual(selected, ['LAMP'])
})

test('without a search the toggle selects and clears everything', () => {
  const allCodes = ['LAMP', 'MUG']
  assert.deepEqual(toggledSelection({ selected: ['LAMP'], allCodes, shownCodes: ['LAMP'], isSearching: false }), allCodes)
  assert.deepEqual(toggledSelection({ selected: allCodes, allCodes, shownCodes: ['LAMP'], isSearching: false }), [])
})
