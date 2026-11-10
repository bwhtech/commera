<script setup>
import { computed, ref, watch } from 'vue'
import { Button, Combobox } from 'frappe-ui'
import Thumb from '../Thumb.vue'
import { usePreviewEntries } from '../../data/themeLayout'
import { __ } from '../../data/translation'

const props = defineProps({
  editor: { type: Object, required: true },
})

const { state, setPreviewEntry } = props.editor

const PAGE_COPY = {
  product: {
    placeholder: __('Search products'),
    empty: __('No products yet'),
    hint: __('Publish a product to see this layout with real content.'),
    create: { label: __('Go to products'), route: { name: 'Products' } },
  },
  search: {
    placeholder: __('Search, or type any term'),
    empty: __('No products yet'),
    hint: __('Publish a product to see search results here.'),
    create: { label: __('Go to products'), route: { name: 'Products' } },
  },
  products: {
    placeholder: __('Search collections'),
    empty: __('No collections yet'),
    hint: __('Every product is still listed under All products.'),
    create: { label: __('Go to collections'), route: { name: 'Collections' } },
  },
  page: {
    placeholder: __('Search pages'),
    empty: __('No pages yet'),
    hint: __('Publish a page to see this layout with real content.'),
    create: { label: __('Create a page'), route: { name: 'StorefrontPageNew' } },
  },
}

const { query, results, entries, current, hasMore, showMore } = usePreviewEntries(state)

const open = ref(false)
watch([open, () => state.page], () => (query.value = ''))

const copy = computed(() => PAGE_COPY[state.page] ?? PAGE_COPY.product)

const options = computed(() => {
  const listed = entries.value.map((entry) => ({ label: entry.title, value: entry.value, image: entry.image }))
  const selected = current.value
  if (selected && !query.value && !listed.some((option) => option.value === selected.value)) {
    listed.unshift({ label: selected.title, value: selected.value })
  }
  return listed
})

const isEmpty = computed(() => results.data && !current.value)

const model = computed({
  get: () => current.value?.value ?? null,
  set: (value) => {
    if (value !== null && value !== undefined && value !== current.value?.value) setPreviewEntry(value)
  },
})
</script>

<template>
  <Combobox
    v-model="model"
    v-model:open="open"
    v-model:query="query"
    :options="options"
    :filterable="false"
    :loading="results.loading && !entries.length"
    :placeholder="copy.placeholder"
    :empty-text="copy.empty"
    align="start"
  >
    <template #trigger>
      <Button
        variant="ghost"
        icon-right="lucide-chevron-down"
        class="max-w-72"
        :aria-label="__('Preview with {0}', [current?.title ?? copy.empty])"
        data-preview-entry-picker
      >
        <span class="flex min-w-0 gap-1">
          <span class="shrink-0 text-ink-gray-5">{{ __('Preview with') }}</span>
          <span class="truncate" :class="current ? 'text-ink-gray-8' : 'text-ink-gray-5'">
            {{ current?.title ?? copy.empty }}
          </span>
        </span>
      </Button>
    </template>
    <template #item-prefix="{ item }">
      <Thumb v-if="item.image" :image="item.image" size="size-6" />
    </template>
    <template #empty>
      <div v-if="isEmpty && !query" class="flex flex-col items-center gap-1 px-3 py-4 text-center">
        <p class="text-base font-medium text-ink-gray-8">{{ copy.empty }}</p>
        <p class="text-p-sm text-ink-gray-5">{{ copy.hint }}</p>
        <Button class="mt-2" :label="copy.create.label" icon-left="lucide-plus" :route="copy.create.route" />
      </div>
      <p v-else class="px-3 py-4 text-center text-p-sm text-ink-gray-5">{{ __('No matches') }}</p>
    </template>
    <template #footer>
      <div v-if="hasMore" class="border-t border-outline-gray-1 p-1">
        <Button class="w-full" variant="ghost" :label="__('Show more')" :loading="results.loading" @click="showMore" />
      </div>
    </template>
  </Combobox>
</template>
