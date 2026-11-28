<script setup>
/**
 * Price and the optional Original price, laid out the same on every price form: Price alone at
 * full width with a ghost "+ Add original price" under it; once added, Original price sits next to
 * Price from `sm` (stacked below on a phone) with a × at the end of its field that clears and hides
 * it again.
 */
import { computed, nextTick, ref } from 'vue'
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

// Adding and removing swap the field and the "+ Add original price" button, and the control that
// had focus unmounts with the swap: focus would fall to the dialog and the next Tab would start
// again at the top of the form. Each side hands focus to what replaced it.
const originalPriceField = ref(null)
const addButton = ref(null)

async function removeOriginalPrice() {
  originalPrice.value = null
  revealed.value = false
  await nextTick()
  addButton.value?.$el?.focus()
}

async function addOriginalPrice() {
  revealed.value = true
  await nextTick()
  originalPriceField.value?.querySelector('input')?.focus()
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
          <span class="text-base text-ink-gray-6">{{ currencySymbol }}</span>
        </template>
      </FormControl>

      <!-- The × sits in the field's own suffix, which frappe-ui centres on the input, so it lines up
           whatever the label, description or error around the input measure. The description fits
           one line in the half-width column; the error states the "higher than the price" rule
           when it is broken. -->
      <div v-if="showOriginalPrice" ref="originalPriceField">
        <FormControl
          v-model.number="originalPrice"
          type="number"
          inputmode="decimal"
          :label="__('Original price')"
          :description="__('Shown crossed out next to the price.')"
          :error="props.originalPriceError"
          placeholder="0"
        >
          <template #prefix>
            <span class="text-base text-ink-gray-6">{{ currencySymbol }}</span>
          </template>
          <template #suffix>
            <Button
              size="xs"
              variant="ghost"
              icon="lucide-x"
              :aria-label="__('Remove original price')"
              :tooltip="__('Remove original price')"
              @click="removeOriginalPrice"
            />
          </template>
        </FormControl>
      </div>
    </div>
    <!-- -ms-2 lines the ghost button's text up with the field labels: its own px-2 would indent it. -->
    <Button
      v-if="!showOriginalPrice"
      ref="addButton"
      class="mt-1.5 -ms-2"
      variant="ghost"
      icon-left="lucide-plus"
      :label="__('Add original price')"
      @click="addOriginalPrice"
    />
  </div>
</template>
