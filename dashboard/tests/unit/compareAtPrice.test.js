import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isCompareAtBelowPrice } from '../../src/data/product.js'

test('a compare-at below the price is flagged', () => {
  assert.equal(isCompareAtBelowPrice(1200, 1000), true)
})

test('a compare-at above or equal to the price passes', () => {
  assert.equal(isCompareAtBelowPrice(1000, 1200), false)
  assert.equal(isCompareAtBelowPrice(1000, 1000), false)
})

test('a blank compare-at or a missing price is not flagged', () => {
  assert.equal(isCompareAtBelowPrice(1000, null), false)
  assert.equal(isCompareAtBelowPrice(1000, ''), false)
  assert.equal(isCompareAtBelowPrice(null, 500), false)
  assert.equal(isCompareAtBelowPrice('', 500), false)
})
