<script setup>
/**
 * The products Publish all left as drafts, each with what it still needs (imports.publish_drafts).
 * Shared by the spreadsheet and ERPNext result screens.
 */
import { Button } from 'frappe-ui'
import { productCount } from '../../data/importCounts'
import { __ } from '../../data/translation'

defineProps({
  products: { type: Array, required: true },
})

const emit = defineEmits(['open'])
</script>

<template>
  <div class="rounded-5 border border-outline-gray-1">
    <div class="border-b border-outline-gray-1 px-4 py-3 text-base-semibold text-ink-gray-8">
      {{ __('{0} not live yet', [productCount(products.length)]) }}
    </div>
    <div v-scroll-fade class="max-h-64 divide-y divide-outline-gray-1 overflow-y-auto">
      <div v-for="product in products" :key="product.item_template" class="flex items-center gap-3 px-4 py-2.5">
        <div class="min-w-0 flex-1">
          <div class="truncate text-base text-ink-gray-8">{{ product.title }}</div>
          <p class="text-p-sm text-ink-gray-6">{{ product.reasons.join(' · ') }}</p>
        </div>
        <Button
          class="shrink-0"
          variant="subtle"
          icon-right="lucide-chevron-right rtl:-scale-x-100"
          :label="__('Open')"
          :aria-label="__('Open {0}', [product.title])"
          @click="emit('open', product.item_template)"
        />
      </div>
    </div>
  </div>
</template>
