import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ref } from 'vue'
import { usePriceDraft } from '../../src/data/priceDraft.js'

const rates = (sale, original = sale) => ({ sale_rate: sale, default_rate: original })

test('opening a color loads its stored price', () => {
  const draft = usePriceDraft(() => rates(40, 50))
  draft.start('Black')
  assert.equal(draft.price.value, 40)
  assert.equal(draft.originalPrice.value, 50)
  assert.equal(draft.isChanged.value, false)
})

test('a price held for Add stock survives the round trip, unsaved', () => {
  const stored = ref(rates(82))
  const draft = usePriceDraft(() => stored.value)
  draft.start('Red')
  draft.price.value = 83
  draft.hold('Red')
  // Saving stock reloads the product: new row objects, same stored price.
  stored.value = rates(82)
  draft.start('Red')
  assert.equal(draft.price.value, 83)
  assert.equal(draft.isChanged.value, true)
  assert.deepEqual(draft.rates.value, { default_rate: 83, sale_rate: 83 })
})

test('the hold is used once: the next open after it reloads the stored price', () => {
  const draft = usePriceDraft(() => rates(82))
  draft.start('Red')
  draft.price.value = 83
  draft.hold('Red')
  draft.start('Red')
  draft.start('Red')
  assert.equal(draft.price.value, 82)
})

test('a hold for one color does not carry into another', () => {
  const draft = usePriceDraft(() => rates(82))
  draft.start('Red')
  draft.price.value = 83
  draft.hold('Red')
  draft.start('Blue')
  assert.equal(draft.price.value, 82)
})

test('a removed original price saves as no crossed-out price', () => {
  const draft = usePriceDraft(() => rates(40, 50))
  draft.start('Black')
  draft.originalPrice.value = null
  assert.equal(draft.isChanged.value, true)
  assert.deepEqual(draft.rates.value, { default_rate: 40, sale_rate: 40 })
})

test('an original price below the price is refused', () => {
  const draft = usePriceDraft(() => rates(40))
  draft.start('Black')
  draft.originalPrice.value = 30
  assert.equal(draft.originalError.value, 'Must be higher than the price.')
  draft.price.value = 0
  assert.equal(draft.priceError.value, 'Enter a price above zero.')
})
