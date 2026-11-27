import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  colorLabel,
  groupSizes,
  isSizesOnly,
  priceScopeHint,
  priceUpdatedMessage,
  stockRows,
  totalStock,
} from '../../src/data/variants.js'

const size = (name, itemCode, stock = 0) => ({ size: name, item_code: itemCode, stock })

test('a color is named by its value, and the hidden color of a sizes-only product has no name', () => {
  assert.equal(colorLabel({ option: 'Black' }), 'Black')
  assert.equal(colorLabel({ option: 'Standard' }), '')
  assert.equal(isSizesOnly({ option: 'Standard' }), true)
  assert.equal(isSizesOnly({ option: 'Black' }), false)
})

test('the price hint names the color only when it has sizes to share the price', () => {
  assert.equal(priceScopeHint({ option: 'Black', sizes: [size('S', 'A'), size('M', 'B')] }), 'Same price for every size of Black.')
  assert.equal(priceScopeHint({ option: 'Standard', sizes: [size('S', 'A')] }), 'Same price for every size.')
  assert.equal(priceScopeHint({ option: 'Black', sizes: [size('One Size', 'A')] }), '')
})

test('a price toast never names the hidden color', () => {
  assert.equal(priceUpdatedMessage({ option: 'Black' }), 'Price updated for Black')
  assert.equal(priceUpdatedMessage({ option: 'Standard' }), 'Price updated')
})

test('the hidden One Size is not a size the seller sees', () => {
  assert.deepEqual(groupSizes({ sizes: [size('One Size', 'TEE-BLK')] }), [])
  assert.deepEqual(groupSizes({ sizes: [size('S', 'TEE-S'), size('M', 'TEE-M')] }).map((row) => row.size), ['S', 'M'])
})

test('a color totals the stock of its sizes', () => {
  assert.equal(totalStock({ sizes: [size('S', 'A', 3), size('M', 'B', 4), { size: 'L', item_code: 'C' }] }), 7)
})

test('stock rows name each variant without placeholder words', () => {
  const rows = stockRows([
    { option: 'Black', sizes: [size('S', 'TEE-BLK-S', 2)] },
    { option: 'White', sizes: [size('One Size', 'TEE-WHT')] },
    { option: 'Standard', sizes: [size('M', 'SOCK-M')] },
  ])
  assert.deepEqual(
    rows.map((row) => [row.id, row.title, row.onHand]),
    [
      ['TEE-BLK-S', 'Black · S', 2],
      ['TEE-WHT', 'White', 0],
      ['SOCK-M', 'M', 0],
    ],
  )
})
