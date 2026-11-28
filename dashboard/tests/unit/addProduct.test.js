import assert from 'node:assert/strict'
import { test } from 'node:test'
import { newProductOptionSizes, pairKey } from '../../src/data/optionSizes.js'
import {
  isOriginalPriceValid,
  listedVariantCount,
  originalPriceError,
  priceInputRates,
  priceInputs,
} from '../../src/data/product.js'

test('sizes with no color become one variant each on the hidden option', () => {
  assert.deepEqual(newProductOptionSizes([], ['S', 'M', 'L'], []), [{ option: 'Standard', sizes: ['S', 'M', 'L'] }])
})

test('a product with no options sends no rows', () => {
  assert.deepEqual(newProductOptionSizes([], [], []), [])
})

test('colors keep their own rows and unticked sizes', () => {
  assert.deepEqual(newProductOptionSizes(['Black', 'White'], ['S', 'M'], [pairKey('White', 'M')]), [
    { option: 'Black', sizes: ['S', 'M'] },
    { option: 'White', sizes: ['S'] },
  ])
})

test('price is what the customer pays, original price only when it is higher', () => {
  assert.deepEqual(priceInputs({ default_rate: 1299, sale_rate: 999 }), { price: 999, originalPrice: 1299 })
  assert.deepEqual(priceInputs({ default_rate: 999, sale_rate: 999 }), { price: 999, originalPrice: null })
  assert.deepEqual(priceInputs({ default_rate: 999, sale_rate: null }), { price: 999, originalPrice: null })
  assert.deepEqual(priceInputs(undefined), { price: null, originalPrice: null })
})

test('an empty original price writes the price to both lists', () => {
  assert.deepEqual(priceInputRates({ price: 999, originalPrice: null }), { default_rate: 999, sale_rate: 999 })
  assert.deepEqual(priceInputRates({ price: 999, originalPrice: 1299 }), { default_rate: 1299, sale_rate: 999 })
})

test('the original price must be higher than the price', () => {
  assert.equal(isOriginalPriceValid({ price: 999, originalPrice: '' }), true)
  assert.equal(isOriginalPriceValid({ price: 999, originalPrice: 1299 }), true)
  assert.equal(isOriginalPriceValid({ price: 999, originalPrice: 999 }), false)
  assert.equal(originalPriceError({ price: 999, originalPrice: 500 }), 'Must be higher than the price.')
  assert.equal(originalPriceError({ price: 999, originalPrice: null }), '')
})

test('the products list counts every color and size pair, and none for a single item', () => {
  const row = (option, sizeCount) => ({ option, size_count: sizeCount })
  assert.equal(listedVariantCount({ variants: [row('Standard', 1)] }), 0)
  assert.equal(listedVariantCount({ variants: [row('Standard', 3)] }), 3)
  assert.equal(listedVariantCount({ variants: [row('Black', 3), row('White', 2)] }), 5)
  assert.equal(listedVariantCount({ variants: [row('Black', 1), row('White', 1)] }), 2)
})
