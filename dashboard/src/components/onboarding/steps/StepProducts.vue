<script setup>
import { computed } from 'vue'
import { Badge, Spinner } from 'frappe-ui'
import { openAddProduct } from '../../../data/addProduct'
import { openImport } from '../../../data/importFlow'
import { storeSetup } from '../../../data/onboarding'

// Both dialogs write Items against the company, which exists only once the store setup is done.
const isStoreReady = computed(() => storeSetup.status === 'done')

const SOURCES = [
  { key: 'shopify', label: 'Import from Shopify', icon: 'lucide-arrow-down-to-line', comingSoon: true },
  { key: 'csv', label: 'Import a CSV', icon: 'lucide-file-spreadsheet', open: () => openImport('onboarding') },
  { key: 'manual', label: 'Add a product', icon: 'lucide-plus', open: openAddProduct },
]
</script>

<template>
  <div class="space-y-2">
    <button
      v-for="source in SOURCES"
      :key="source.key"
      type="button"
      class="flex w-full items-center gap-3 rounded-5 border border-outline-gray-2 px-3 py-3 text-left transition-[background-color,transform] duration-150 ease-out-strong enabled:hover:bg-surface-gray-1 enabled:active:scale-[0.99] disabled:cursor-not-allowed"
      :disabled="source.comingSoon || !isStoreReady"
      :data-onboarding-source="source.key"
      @click="source.open()"
    >
      <span :class="source.icon" class="size-4 text-ink-gray-6" aria-hidden="true" />
      <span class="flex-1 text-base" :class="source.comingSoon ? 'text-ink-gray-5' : 'text-ink-gray-8'">{{ source.label }}</span>
      <Badge v-if="source.comingSoon" label="Coming soon" theme="gray" variant="subtle" />
      <Spinner v-else-if="!isStoreReady" class="size-4 text-ink-gray-5" />
      <span v-else class="lucide-chevron-right size-4 text-ink-gray-5" aria-hidden="true" />
    </button>
  </div>
</template>
