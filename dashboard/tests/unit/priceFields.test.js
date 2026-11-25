import assert from 'node:assert/strict'
import { test } from 'node:test'
import { hasPrice, isPriceValid, priceFields, priceRates } from '../../src/data/product.js'

test('a discounted product loads as its price and what the shopper pays', () => {
  assert.deepEqual(priceFields({ default_rate: 1299, sale_rate: 999 }), { price: 1299, discountedPrice: 999 })
})

test('products without a crossed-out price load with the price the shopper pays as the discounted price', () => {
  assert.deepEqual(priceFields({ default_rate: null, sale_rate: 999 }), { price: null, discountedPrice: 999 })
  assert.deepEqual(priceFields({ default_rate: 1299, sale_rate: null }), { price: null, discountedPrice: 1299 })
  assert.deepEqual(priceFields({ default_rate: 999, sale_rate: 999 }), { price: null, discountedPrice: 999 })
  assert.deepEqual(priceFields({ default_rate: 800, sale_rate: 999 }), { price: null, discountedPrice: 999 })
  assert.deepEqual(priceFields(undefined), { price: null, discountedPrice: null })
})

test('a price above the discounted price saves as the crossed-out rate', () => {
  assert.deepEqual(priceRates({ price: 1299, discountedPrice: 999 }), { default_rate: 1299, sale_rate: 999 })
})

test('an empty price charges the discounted price and crosses nothing out', () => {
  for (const price of [null, '', 0]) {
    const rates = priceRates({ price, discountedPrice: 999 })
    assert.deepEqual(rates, { default_rate: 999, sale_rate: 999 })
    assert.equal(priceFields(rates).price, null)
  }
})

test('every loaded shape saves back to what it loaded from', () => {
  for (const rated of [
    { default_rate: 1299, sale_rate: 999 },
    { default_rate: null, sale_rate: 999 },
    { default_rate: 1299, sale_rate: null },
    { default_rate: 999, sale_rate: 999 },
  ]) {
    const saved = priceRates(priceFields(rated))
    assert.deepEqual(priceFields(saved), priceFields(rated), JSON.stringify(rated))
  }
})

test('a price must be above the discounted price', () => {
  assert.equal(isPriceValid({ price: 1299, discountedPrice: 999 }), true)
  assert.equal(isPriceValid({ price: null, discountedPrice: 999 }), true)
  assert.equal(isPriceValid({ price: '', discountedPrice: 999 }), true)
  assert.equal(isPriceValid({ price: 999, discountedPrice: 999 }), false)
  assert.equal(isPriceValid({ price: 999, discountedPrice: 1299 }), false)
})

test('a missing discounted price is refused', () => {
  for (const discountedPrice of [null, undefined, '', 0]) assert.equal(hasPrice(discountedPrice), false)
  assert.equal(hasPrice(999), true)
})
