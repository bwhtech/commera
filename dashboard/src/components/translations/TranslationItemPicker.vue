<script setup>
import { computed, ref, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { Button, Dropdown, TabButtons, TextInput } from 'frappe-ui'
import TranslationStatusDot from './TranslationStatusDot.vue'
import { searchTranslations } from '../../data/translations'
import { describeResource, itemProgress, progressStatus } from '../../data/translationStatus'
import { createSequence } from '../../utils/sequence'
import { errorMessage } from '../../data/errors'
import { __ } from '../../data/translation'

// The left pane: which resource, its records, and a search across every resource.
const props = defineProps({
  disabled: { type: Boolean, default: false },
  language: { type: Object, required: true },
  resource: { type: Object, required: true },
  resourceGroups: { type: Array, required: true },
  items: { type: Array, required: true },
  total: { type: Number, default: 0 },
  toDoCount: { type: Number, default: 0 },
  selectedName: { type: String, default: '' },
  hasMore: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  loaded: { type: Boolean, default: false },
  loadError: { type: Object, default: null },
  // Unsaved values by fieldKey(), so a record's dot shows edits before they are saved.
  pending: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['select', 'open', 'load-more', 'retry'])
const filter = defineModel('filter', { type: String, default: 'todo' })

const resourceMenu = computed(() =>
  props.resourceGroups.map((group) => ({
    group: group.label,
    options: group.resources.map((resource) => ({
      label: resource.label,
      icon: resource.icon,
      disabled: props.disabled,
      onClick: () => { if (!props.disabled) emit('open', resource.type) },
    })),
  })),
)

const searchText = ref('')
const results = ref([])
const searches = createSequence()
const runSearch = useDebounceFn(async (text) => {
  const ticket = searches.next()
  const found = text.trim() ? await searchTranslations(props.language.code, text) : []
  if (searches.isLatest(ticket)) results.value = (found ?? []).map((group) => ({
    ...group,
    ...describeResource({ type: group.resource, label: group.label }),
  }))
}, 300)
watch(searchText, runSearch)
watch(() => props.language.code, () => (searchText.value = ''))

function openResult(resource, name) {
  if (props.disabled) return
  searchText.value = ''
  emit('open', resource, name)
}

// Records matching the filter; the list may hold only the first pages of them.
const matchingCount = computed(() => (filter.value === 'todo' ? props.toDoCount : props.total))

const rows = computed(() =>
  props.items.map((item) => {
    const progress = itemProgress(item, props.pending, props.language.code, props.resource.type)
    return { item, progress, status: progressStatus(progress) }
  }),
)
</script>

<template>
  <div class="flex min-h-0 flex-col">
    <div class="space-y-2 p-3">
      <Dropdown :disabled="disabled" :options="resourceMenu" match-trigger-width>
        <!-- Button centres its content; the chevron's auto margin takes the free space instead,
             which holds the icon and label at the start and the chevron at the end. -->
        <Button :disabled="disabled" class="w-full" :icon-left="resource.icon" :aria-label="__('Resource: {0}', [resource.label])">
          {{ resource.label }}
          <template #suffix><span class="lucide-chevron-down ms-auto size-4 shrink-0" aria-hidden="true" /></template>
        </Button>
      </Dropdown>
      <TextInput :disabled="disabled" v-model="searchText" type="search" :placeholder="__('Search all resources')" :aria-label="__('Search all resources')">
        <template #prefix><span class="lucide-search size-4 text-ink-gray-5" aria-hidden="true" /></template>
      </TextInput>
    </div>

    <div v-if="searchText.trim()" class="min-h-0 flex-1 overflow-y-auto px-2 pb-6">
      <p v-if="!results.length" class="px-2 text-p-sm text-ink-gray-5">{{ __('Nothing matches “{0}”', [searchText.trim()]) }}</p>
      <div v-for="group in results" :key="group.resource" class="mb-3">
        <p class="flex items-center gap-1.5 px-2 pb-1 text-sm text-ink-gray-5">
          <span :class="[group.icon, 'size-3.5']" aria-hidden="true" />
          {{ group.label }}
          <span class="ms-auto tabular-nums">{{ group.records.length }}</span>
        </p>
        <button
          v-for="record in group.records"
          :key="record.name"
          :disabled="disabled"
          type="button"
          class="block w-full truncate rounded-4 px-2 py-1.5 text-start text-base text-ink-gray-8 hover:bg-surface-gray-2"
          @click="openResult(group.resource, record.name)"
        >
          {{ record.title }}
        </button>
      </div>
    </div>

    <template v-else>
      <div class="flex items-center gap-2 px-3 pb-2">
        <p class="text-sm text-ink-gray-5">{{ __('Showing {0} of {1}', [items.length, matchingCount]) }}</p>
        <TabButtons
          v-model="filter"
          :disabled="disabled"
          class="ms-auto"
          :options="[
            { label: __('To do'), value: 'todo', disabled },
            { label: __('All'), value: 'all', disabled },
          ]"
        />
      </div>
      <ul class="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-6">
        <li v-for="{ item, progress, status } in rows" :key="item.name">
          <button
            :disabled="disabled"
            type="button"
            class="flex w-full items-center gap-2 rounded-4 px-2 py-2 text-start hover:bg-surface-gray-2"
            :class="{ 'bg-surface-gray-3': item.name === selectedName }"
            :aria-current="item.name === selectedName ? 'true' : undefined"
            @click="emit('select', item.name)"
          >
            <span class="min-w-0 flex-1 truncate text-base text-ink-gray-8">{{ item.title }}</span>
            <span v-if="status === 'current'" class="lucide-check size-3.5 text-ink-green-5" :aria-label="__('Up to date')" />
            <span
              v-else
              class="flex items-center gap-1.5 text-sm tabular-nums text-ink-gray-5"
              :aria-label="status === 'unsaved' ? __('Unsaved changes') : undefined"
            >
              <TranslationStatusDot :status="status" />
              <template v-if="progress.toDo">{{ progress.toDo }}</template>
            </span>
          </button>
        </li>
        <li v-if="hasMore" class="px-2 pt-2">
          <Button :disabled="disabled" class="w-full" :label="__('Load more')" :loading="loading" @click="emit('load-more')" />
        </li>
        <li v-if="loadError" class="px-2 py-6 text-center" role="alert">
          <p class="text-p-sm text-ink-red-6">{{ errorMessage(loadError, __('Could not load translations')) }}</p>
          <Button :disabled="disabled" class="mt-2" size="sm" :label="__('Retry')" @click="emit('retry')" />
        </li>
        <li v-else-if="loaded && !loading && !items.length && !total" class="px-2 py-6 text-center">
          <p class="text-p-sm text-ink-gray-5">{{ __('Nothing to translate here') }}</p>
        </li>
        <li v-else-if="loaded && !loading && !items.length" class="px-2 py-6 text-center">
          <p class="text-p-sm text-ink-gray-5">{{ __('{0} are up to date in {1}', [resource.label, language.name]) }}</p>
          <Button :disabled="disabled" v-if="filter === 'todo' && total" class="mt-2" size="sm" :label="__('Show all')" @click="filter = 'all'" />
        </li>
      </ul>
    </template>
  </div>
</template>
