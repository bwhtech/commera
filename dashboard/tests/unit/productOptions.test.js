import assert from 'node:assert/strict'
import { test } from 'node:test'
import { optionChanges, pairKey } from '../../src/data/optionSizes.js'
import { productOptions, useProductStats } from '../../src/data/product.js'

const variant = (option, sizes) => ({ option, sizes: sizes.map((size) => ({ size })) })

test('a product created without options has none to show', () => {
  const product = { variants: [variant('Standard', ['One Size'])] }
  assert.deepEqual(productOptions(product), { options: [], sizes: [] })
})

test('colors and sizes are listed once each, in variant order', () => {
  const product = { variants: [variant('Indigo', ['S', 'M']), variant('Sand', ['M', 'L'])] }
  assert.deepEqual(productOptions(product), { options: ['Indigo', 'Sand'], sizes: ['S', 'M', 'L'] })
})

test('sizes without a color drop the placeholder color only', () => {
  const product = { variants: [variant('Standard', ['S', 'M'])] }
  assert.deepEqual(productOptions(product), { options: [], sizes: ['S', 'M'] })
})

test('colors without sizes drop the placeholder size only', () => {
  const product = { variants: [variant('Indigo', ['One Size']), variant('Sand', ['One Size'])] }
  assert.deepEqual(productOptions(product), { options: ['Indigo', 'Sand'], sizes: [] })
})

const pairs = (list) => list.map(([option, size]) => ({ option, size }))
const single = pairs([['Standard', 'One Size']])

test('a first colour replaces the hidden single item', () => {
  const changes = optionChanges({ live: single, options: ['Red', 'Blue'], sizes: [], excluded: [], keepsHiddenOption: true })
  assert.deepEqual(changes.added, pairs([['Red', 'One Size'], ['Blue', 'One Size']]))
  assert.deepEqual(changes.removed, single)
})

test('first sizes keep the hidden option', () => {
  const changes = optionChanges({ live: single, options: [], sizes: ['S', 'M'], excluded: [], keepsHiddenOption: true })
  assert.deepEqual(changes.added, pairs([['Standard', 'S'], ['Standard', 'M']]))
  assert.deepEqual(changes.removed, single)
})

test('an untouched product without options changes nothing', () => {
  const changes = optionChanges({ live: single, options: [], sizes: [], excluded: [], keepsHiddenOption: true })
  assert.deepEqual([changes.added, changes.removed], [[], []])
})

test('a product with colours never gains the hidden option when they are all cleared', () => {
  const live = pairs([['Red', 'S']])
  const changes = optionChanges({ live, options: [], sizes: ['S'], excluded: [], keepsHiddenOption: false })
  assert.deepEqual(changes.ticked, [])
  assert.deepEqual(changes.removed, live)
})

test('an unticked pair is neither added nor kept', () => {
  const live = pairs([['Red', 'S'], ['Red', 'M']])
  const changes = optionChanges({
    live,
    options: ['Red'],
    sizes: ['S', 'M'],
    excluded: [pairKey('Red', 'M')],
    keepsHiddenOption: false,
  })
  assert.deepEqual([changes.added, changes.removed], [[], pairs([['Red', 'M']])])
})

test('a color that skips sizes does not reorder them', () => {
  const product = { variants: [variant('Black', ['M', 'L']), variant('White', ['S', 'M', 'L'])] }
  assert.deepEqual(productOptions(product).sizes, ['S', 'M', 'L'])
})

test('the store size order wins over what sparse colors imply', () => {
  const product = {
    size_order: ['S', 'M', 'L'],
    variants: [variant('Red', ['S', 'M']), variant('Blue', ['S', 'L'])],
  }
  assert.deepEqual(productOptions(product).sizes, ['S', 'M', 'L'])
})

test('the store size order drops the placeholder size', () => {
  const product = { size_order: ['One Size'], variants: [variant('Indigo', ['One Size'])] }
  assert.deepEqual(productOptions(product).sizes, [])
})

test('the price range leaves out a size with no price, so it never reads ₹0', () => {
  const sized = (option, rates) => ({ option, sizes: rates.map((sale_rate, index) => ({ size: `S${index}`, sale_rate })) })
  const stats = useProductStats({ variants: [sized('Black', [null, 0]), sized('White', [999, 1299])] })
  assert.equal(stats.value.priceLow, 999)
  assert.equal(stats.value.priceHigh, 1299)
  const unpriced = useProductStats({ variants: [sized('Black', [null, 0])] })
  assert.equal(unpriced.value.priceLow, null)
})
