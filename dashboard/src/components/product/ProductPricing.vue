<script setup>
import { computed, ref } from 'vue'
import { Button, FormControl } from 'frappe-ui'
import ProductSection from './ProductSection.vue'
import ReceiveStockDialog from './ReceiveStockDialog.vue'
import { symbolFor } from '../../data/format'
import { hasPrice } from '../../data/product'

// Price and stock for a product sold as one item, edited here instead of through a variant
// dialog naming the placeholder variant. The prices are part of the page's draft and save with
// Save; stock is added straight away, as everywhere else.
const props = defineProps({
  product: { type: Object, required: true },
  draft: { type: Object, required: true },
  priceError: { type: String, default: '' },
  originalPriceError: { type: String, default: '' },
})
const emit = defineEmits(['received'])

const currencySymbol = symbolFor()
// Revealed once, it stays: clearing the field while typing must not make it vanish.
const originalPriceRevealed = ref(hasPrice(props.draft.originalPrice))
const showOriginalPrice = computed(() => originalPriceRevealed.value || hasPrice(props.draft.originalPrice))
const receiveOpen = ref(false)

const size = computed(() => props.product.variants[0].sizes[0])
const stockRows = computed(() => [{ id: size.value.item_code, title: props.product.title, onHand: size.value.stock ?? 0 }])
</script>

<template>
  <ProductSection :title="__('Price and stock')">
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <FormControl
        v-model="draft.price"
        type="number"
        inputmode="decimal"
        :label="__('Price')"
        :error="priceError"
        required
      >
        <template #prefix>
          <span class="text-base text-ink-gray-5">{{ currencySymbol }}</span>
        </template>
      </FormControl>

      <FormControl
        v-if="showOriginalPrice"
        v-model="draft.originalPrice"
        type="number"
        inputmode="decimal"
        :label="__('Original price')"
        :description="__('Shown crossed out next to the price. Must be higher than the price.')"
        :error="originalPriceError"
      >
        <template #prefix>
          <span class="text-base text-ink-gray-5">{{ currencySymbol }}</span>
        </template>
      </FormControl>
      <div v-else class="flex items-end">
        <Button
          variant="ghost"
          icon-left="lucide-plus"
          :label="__('Add original price')"
          @click="originalPriceRevealed = true"
        />
      </div>
    </div>

    <div class="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-outline-gray-1 pt-4">
      <div>
        <p class="text-base text-ink-gray-8 tabular-nums">{{ __('{0} in stock', [size.stock ?? 0]) }}</p>
        <p v-if="size.committed" class="mt-0.5 text-sm text-ink-gray-5 tabular-nums">
          {{ __('{0} ordered, not shipped', [size.committed]) }}
        </p>
      </div>
      <Button :label="__('Add stock')" icon-left="lucide-package-plus" @click="receiveOpen = true" />
    </div>

    <ReceiveStockDialog v-model:open="receiveOpen" :rows="stockRows" @received="emit('received')" />
  </ProductSection>
</template>
