<script setup>
/**
 * Price and the optional Original price, laid out the same on every price form: Price alone at
 * full width with a ghost "+ Add original price" under it; once added, Original price sits next to
 * Price from `sm` (stacked below on a phone) with a × that clears and hides it again.
 */
import { computed, ref } from 'vue'
import { Button, FormControl } from 'frappe-ui'
import { symbolFor } from '../data/format'
import { hasPrice } from '../data/product'
import { __ } from '../data/translation'

const props = defineProps({
  priceError: { type: String, default: '' },
  originalPriceError: { type: String, default: '' },
  // A line under Price, such as "Same price for every size of Black."
  priceDescription: { type: String, default: '' },
})

const price = defineModel('price', { default: null })
const originalPrice = defineModel('originalPrice', { default: null })

const currencySymbol = symbolFor()
// Revealed, it stays while the field is cleared mid-typing; a stored value shows it on its own.
const revealed = ref(false)
const showOriginalPrice = computed(() => revealed.value || hasPrice(originalPrice.value))

function removeOriginalPrice() {
  originalPrice.value = null
  revealed.value = false
}
</script>

<template>
  <div>
    <div class="grid grid-cols-1 items-start gap-4" :class="{ 'sm:grid-cols-2': showOriginalPrice }">
      <FormControl
        v-model.number="price"
        type="number"
        inputmode="decimal"
        :label="__('Price')"
        placeholder="0"
        :error="props.priceError"
        :description="props.priceDescription || undefined"
        required
      >
        <template #prefix>
          <span class="text-base text-ink-gray-5">{{ currencySymbol }}</span>
        </template>
      </FormControl>

      <div v-if="showOriginalPrice" class="flex items-start gap-1">
        <FormControl
          v-model.number="originalPrice"
          class="min-w-0 flex-1"
          type="number"
          inputmode="decimal"
          :label="__('Original price')"
          :description="__('Shown crossed out next to the price. Must be higher than the price.')"
          :error="props.originalPriceError"
          placeholder="0"
        >
          <template #prefix>
            <span class="text-base text-ink-gray-5">{{ currencySymbol }}</span>
          </template>
        </FormControl>
        <!-- mt-6 drops the × past the field label so it sits level with the input. -->
        <Button
          class="mt-6"
          variant="ghost"
          icon="lucide-x"
          :aria-label="__('Remove original price')"
          :tooltip="__('Remove original price')"
          @click="removeOriginalPrice"
        />
      </div>
    </div>
    <!-- -ms-2 lines the ghost button's text up with the field labels: its own px-2 would indent it. -->
    <Button
      v-if="!showOriginalPrice"
      class="mt-1.5 -ms-2"
      variant="ghost"
      icon-left="lucide-plus"
      :label="__('Add original price')"
      @click="revealed = true"
    />
  </div>
</template>
