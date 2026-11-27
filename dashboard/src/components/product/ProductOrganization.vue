<script setup>
import { computed } from 'vue'
import TagMultiSelect from '../TagMultiSelect.vue'
import ProductSection from './ProductSection.vue'
import { useCollections } from '../../data/collections'
import { __ } from '../../data/translation'

const props = defineProps({
  draft: { type: Object, required: true },
  layout: { type: String, default: 'stacked' },
})

const { collectionOptions, load: loadCollections } = useCollections()
loadCollections()

// The first collection is Item.item_group, which the storefront's breadcrumb and size chart read.
// With a single collection there is no choice to explain, so the star and its hint wait for a second.
const hasMainCollection = computed(() => props.draft.collections.length > 1)
const mainIcon = (option, index) => (hasMainCollection.value && index === 0 ? 'lucide-star' : null)
const hint = computed(() =>
  hasMainCollection.value
    ? __('The starred collection is the main one. Your store shows it in the product’s breadcrumb.')
    : '',
)
</script>

<template>
  <ProductSection v-if="layout === 'stacked'" :title="__('Collections')">
    <TagMultiSelect
      v-model="draft.collections"
      class="w-full"
      :placeholder="__('Add a collection')"
      :options="collectionOptions"
      :tag-icon="mainIcon"
    />
    <p v-if="hint" class="mt-1.5 text-p-sm text-ink-gray-5">{{ hint }}</p>
  </ProductSection>

  <section v-else class="border-b border-outline-gray-1 px-4 py-4">
    <TagMultiSelect
      v-model="draft.collections"
      class="w-full"
      :label="__('Collections')"
      :placeholder="__('Add a collection')"
      :options="collectionOptions"
      :tag-icon="mainIcon"
    />
    <p v-if="hint" class="mt-1.5 text-p-sm text-ink-gray-5">{{ hint }}</p>
  </section>
</template>
