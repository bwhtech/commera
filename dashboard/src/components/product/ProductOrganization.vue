<script setup>
import { computed } from 'vue'
import { MultiSelect, Select } from 'frappe-ui'
import { useCollections } from '../../data/collections'

const props = defineProps({
  product: { type: Object, required: true },
  layout: { type: String, default: 'stacked' },
})

const statusOptions = [
  { label: 'Active', value: 'active' },
  { label: 'Draft', value: 'draft' },
  { label: 'Archived', value: 'archived' },
]

const { collectionOptions, load: loadCollections } = useCollections()
loadCollections()

// The first collection is the primary one (Item.item_group): breadcrumbs, size charts and the
// product page's own collection read it. MultiSelect keeps values in the order they were picked,
// and its trigger collapses to "N selected", so the description names the primary.
const primaryHint = computed(() =>
  props.product.collections?.length
    ? `${props.product.collections[0]} is the primary collection, the first one picked.`
    : 'The first collection picked is the primary one.',
)
</script>

<template>
  <section :class="layout === 'stacked' ? '' : 'space-y-4'">
    <h2 v-if="layout === 'stacked'" class="text-lg-semibold text-ink-gray-8">Organisation</h2>
    <h3 v-else class="text-sm text-ink-gray-5">Organisation</h3>

    <div :class="layout === 'stacked' ? 'mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2' : 'mt-4 space-y-4'">
      <!-- Status is read-only here: it is really Item.disabled, and the page's
           "Archive"/"Restore from archive" action (in the ⋯ menu) is the one real
           write path for it — a second editable control here would just race it. -->
      <Select :model-value="product.status" class="w-full" label="Status" :options="statusOptions" disabled />
      <MultiSelect
        v-model="product.collections"
        class="w-full"
        :class="layout === 'stacked' ? 'sm:col-span-2' : ''"
        label="Collections"
        :description="primaryHint"
        :options="collectionOptions"
      />
    </div>
  </section>
</template>
