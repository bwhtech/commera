import { computed, ref } from 'vue'
import { hasPrice, originalPriceError, priceInputRates, priceInputs } from './product.js'
import { __ } from './translation.js'

/**
 * The Price and Original price being edited for one color, read from `rated()` (the size row that
 * holds its stored rates). `start(key)` loads the stored rates on open; `hold(key)` before stepping
 * out to another dialog makes the next `start` for the same key resume the draft instead.
 */
export function usePriceDraft(rated) {
  const price = ref(null)
  const originalPrice = ref(null)
  const stored = computed(() => priceInputs(rated()))
  let heldFor = null

  function start(key) {
    const resumes = heldFor === key
    heldFor = null
    if (resumes) return
    price.value = stored.value.price
    originalPrice.value = stored.value.originalPrice
  }

  function hold(key) {
    heldFor = key
  }

  const inputs = computed(() => ({ price: price.value, originalPrice: originalPrice.value }))
  const priceError = computed(() => (hasPrice(price.value) ? '' : __('Enter a price above zero.')))
  const originalError = computed(() => originalPriceError(inputs.value))
  const isChanged = computed(
    () =>
      Number(price.value) !== Number(stored.value.price) ||
      Number(originalPrice.value || 0) !== Number(stored.value.originalPrice || 0),
  )
  const rates = computed(() => priceInputRates(inputs.value))

  return {
    price,
    originalPrice,
    priceError,
    originalError,
    isChanged,
    rates,
    start,
    hold,
  }
}
