<script setup>
import TagMultiSelect from '../TagMultiSelect.vue'
import { useCollections } from '../../data/collections'
import { __ } from '../../data/translation'

defineProps({
  product: { type: Object, required: true },
  layout: { type: String, default: 'stacked' },
})

const { collectionOptions, load: loadCollections } = useCollections()
loadCollections()

// The first collection is the primary one (Item.item_group).
const primaryIcon = (option, index) => (index === 0 ? 'lucide-star' : null)
</script>

<template>
  <section :class="layout === 'stacked' ? '' : 'border-b border-outline-gray-1 px-4 py-4'">
    <h2 v-if="layout === 'stacked'" class="text-lg-semibold text-ink-gray-8">{{ __('Organisation') }}</h2>
    <h3 v-else class="text-sm text-ink-gray-5">{{ __('Organisation') }}</h3>

    <div :class="layout === 'stacked' ? 'mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2' : 'mt-3 space-y-4'">
      <TagMultiSelect
        v-model="product.collections"
        class="w-full"
        :class="layout === 'stacked' ? 'sm:col-span-2' : ''"
        :label="__('Collections')"
        :description="__('The starred collection is the primary one.')"
        :placeholder="__('Add a collection')"
        :options="collectionOptions"
        :tag-icon="primaryIcon"
      />
    </div>
  </section>
</template>
