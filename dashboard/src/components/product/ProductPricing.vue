<script setup>
import { computed, ref } from 'vue'
import { Button } from 'frappe-ui'
import PriceFields from '../PriceFields.vue'
import ProductSection from './ProductSection.vue'
import ReceiveStockDialog from './ReceiveStockDialog.vue'

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

const receiveOpen = ref(false)

const size = computed(() => props.product.variants[0].sizes[0])
const stockRows = computed(() => [{ id: size.value.item_code, title: props.product.title, onHand: size.value.stock ?? 0 }])
</script>

<template>
  <ProductSection id="product-pricing" :title="__('Price and stock')">
    <PriceFields
      v-model:price="draft.price"
      v-model:original-price="draft.originalPrice"
      :price-error="priceError"
      :original-price-error="originalPriceError"
    />

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
