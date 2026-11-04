<script setup>
import { computed } from 'vue'
import { MultiSelect, Select } from 'frappe-ui'
import { useCollections } from '../../data/collections'
import { __ } from '../../data/translation'

const props = defineProps({
  product: { type: Object, required: true },
  layout: { type: String, default: 'stacked' },
})

const statusOptions = [
  { label: __('Active'), value: 'active' },
  { label: __('Draft'), value: 'draft' },
  { label: __('Archived'), value: 'archived' },
]

const { collectionOptions, load: loadCollections } = useCollections()
loadCollections()

// The first pick is the primary collection (Item.item_group). The trigger collapses to
// "N selected", so the description lists the picks and marks the primary.
const collectionsHint = computed(() => {
  const [primary, ...others] = props.product.collections ?? []
  if (!primary) return __('The first collection picked is the primary one.')
  return [__('{0} (primary)', [primary]), ...others].join(', ')
})
</script>

<template>
  <section :class="layout === 'stacked' ? '' : 'border-b border-outline-gray-1 px-4 py-4'">
    <h2 v-if="layout === 'stacked'" class="text-lg-semibold text-ink-gray-8">{{ __('Organisation') }}</h2>
    <h3 v-else class="text-sm text-ink-gray-5">{{ __('Organisation') }}</h3>

    <div :class="layout === 'stacked' ? 'mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2' : 'mt-3 space-y-4'">
      <!-- Status is read-only here: it is really Item.disabled, and the page's
           "Archive"/"Restore from archive" action (in the ⋯ menu) is the one real
           write path for it — a second editable control here would just race it. -->
      <Select :model-value="product.status" class="w-full" :label="__('Status')" :options="statusOptions" disabled />
      <MultiSelect
        v-model="product.collections"
        class="w-full"
        :class="layout === 'stacked' ? 'sm:col-span-2' : ''"
        :label="__('Collections')"
        :description="collectionsHint"
        :options="collectionOptions"
      />
    </div>
  </section>
</template>
