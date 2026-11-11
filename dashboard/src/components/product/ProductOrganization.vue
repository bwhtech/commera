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

// Item.item_group is a single collection, not the mock's array of them — the
// MultiSelect widget stays (it is the approved control), wrapped around one
// value, so picking a second collection here replaces the first rather than
// adding to it.
const productCollections = computed({
  get: () => (props.product.collection ? [props.product.collection] : []),
  set: (values) => {
    props.product.collection = values.at(-1) ?? null
  },
})
</script>

<template>
  <section :class="layout === 'stacked' ? '' : 'space-y-4'">
    <h2 v-if="layout === 'stacked'" class="text-lg-semibold text-ink-gray-8">{{ __('Organisation') }}</h2>
    <h3 v-else class="text-sm text-ink-gray-5">{{ __('Organisation') }}</h3>

    <div :class="layout === 'stacked' ? 'mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2' : 'mt-4 space-y-4'">
      <!-- Status is read-only here: it is really Item.disabled, and the page's
           "Archive"/"Restore from archive" action (in the ⋯ menu) is the one real
           write path for it — a second editable control here would just race it. -->
      <Select :model-value="product.status" class="w-full" :label="__('Status')" :options="statusOptions" disabled />
      <MultiSelect
        v-model="productCollections"
        class="w-full"
        :class="layout === 'stacked' ? 'sm:col-span-2' : ''"
        :label="__('Collections')"
        :options="collectionOptions"
      />
    </div>
  </section>
</template>
