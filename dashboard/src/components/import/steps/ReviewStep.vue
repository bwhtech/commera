<script setup>
import { computed } from 'vue'
import { Badge, TabButtons } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import { imp } from '../../../data/importFlow'
import { reviewSummary, showsOriginalPrice, visibleFilter } from '../../../data/importCounts'
import { money } from '../../../data/format'
import { __ } from '../../../data/translation'
import { useIsMobile } from '../../../utils/useIsMobile'
import DotList from '../../DotList.vue'
import Thumb from '../../Thumb.vue'

const isMobile = useIsMobile()

const filters = {
  all: () => true,
  ready: (row) => !row.issue,
  warnings: (row) => row.issue?.level === 'warning',
  errors: (row) => row.issue?.level === 'error',
}
// Only the buckets that hold a row: a tab that is always empty is noise.
const filterOptions = computed(() =>
  [
    { label: __('All rows'), value: 'all' },
    imp.counts.ready && { label: __('Ready'), value: 'ready' },
    imp.counts.warnings && { label: __('Warnings'), value: 'warnings' },
    imp.counts.errors && { label: __('Errors'), value: 'errors' },
  ].filter(Boolean),
)

const activeFilter = computed({
  get: () => visibleFilter(imp.reviewFilter, filterOptions.value),
  set: (filter) => (imp.reviewFilter = filter),
})
const filtered = computed(() => imp.rows.filter(filters[activeFilter.value]))

// The skipped count is always last, and red.
const summary = computed(() => {
  const parts = reviewSummary(imp.counts)
  if (!imp.counts.errors) return parts
  return [...parts.slice(0, -1), { label: parts.at(-1), class: 'text-ink-red-6' }]
})

const optionsOf = (row) => [row.color, row.size].filter(Boolean).join(' · ')
const coverOf = (row) => imp.imageAssignments[row.image_key]?.[0] ?? null
const priceOf = (row) => (row.sale_price ? money(row.sale_price) : '—')
const originalPriceOf = (row) => (showsOriginalPrice(row) ? money(row.compare_at_price) : '')
const mobileFactsOf = (row) =>
  [row.color, row.size, { label: priceOf(row), original: originalPriceOf(row) }, __('Row {0}', [row.row])].filter(Boolean)
const statusTheme = (row) => (!row.issue ? 'green' : row.issue.level === 'error' ? 'red' : 'amber')
const statusLabel = (row) => (!row.issue ? __('Ready') : row.issue.level === 'error' ? __('Skipped') : __('Warning'))
</script>

<template>
  <div class="space-y-5">
    <div>
      <h2 class="text-lg-semibold text-ink-gray-9">{{ __('Check before importing') }}</h2>
      <p class="mt-1.5 text-p-base text-ink-gray-6">
        {{ __('Nothing is saved yet. Every product is added as not published, so nothing is on your store until you publish it. Rows with an error are skipped.') }}
      </p>
    </div>

    <DotList class="text-base text-ink-gray-8" :parts="summary" />

    <TabButtons v-if="filterOptions.length > 2" v-model="activeFilter" :options="filterOptions" />

    <div class="overflow-hidden rounded-5 border border-outline-gray-1">
      <!-- Below sm each row is a stacked card: the five columns cannot share 390px, and the
           problem text has to wrap rather than hide behind a tooltip a finger cannot hover. -->
      <div v-if="isMobile" class="divide-y divide-outline-gray-1">
        <div v-for="item in filtered" :key="item.row" class="flex gap-3 px-4 py-3">
          <Thumb :image="coverOf(item)" size="size-10" />
          <div class="min-w-0 flex-1">
            <div class="flex items-start gap-2">
              <div class="min-w-0 flex-1 truncate text-base text-ink-gray-8">{{ item.title || '—' }}</div>
              <Badge class="shrink-0" :label="statusLabel(item)" :theme="statusTheme(item)" variant="subtle" />
            </div>
            <DotList class="mt-0.5 text-sm text-ink-gray-5" :parts="mobileFactsOf(item)" v-slot="{ part }">
              {{ part.label ?? part }}<s v-if="part.original" class="ms-1 text-ink-gray-4">{{ part.original }}</s>
            </DotList>
            <p v-if="item.issue" class="mt-1 text-p-sm text-ink-gray-7">{{ item.issue.text }}</p>
          </div>
        </div>
      </div>

      <div v-else class="px-2">
        <!-- Rows grow with their problem text, which wraps under the badge instead of hiding in a tooltip. -->
        <List :columns="['minmax(0,1fr)', '9rem', '8rem', '4rem', 'minmax(0,16rem)']">
          <ListHeader>
            <ListHeaderCell>{{ __('Product') }}</ListHeaderCell>
            <ListHeaderCell>{{ __('Collection') }}</ListHeaderCell>
            <ListHeaderCell>{{ __('Price') }}</ListHeaderCell>
            <ListHeaderCell>{{ __('Stock') }}</ListHeaderCell>
            <ListHeaderCell>{{ __('Status') }}</ListHeaderCell>
          </ListHeader>
          <ListRows :items="filtered" row-key="row" v-slot="{ item }">
            <ListRow :value="String(item.row)">
              <ListCell>
                <div class="flex min-w-0 items-center gap-2.5 py-2.5">
                  <Thumb :image="coverOf(item)" size="size-8" />
                  <div class="min-w-0">
                    <div class="truncate text-base text-ink-gray-8">{{ item.title || '—' }}</div>
                    <div class="truncate text-sm text-ink-gray-5">
                      {{ [optionsOf(item), __('Row {0}', [item.row])].filter(Boolean).join(' · ') }}
                    </div>
                  </div>
                </div>
              </ListCell>
              <ListCell><span class="truncate text-sm text-ink-gray-7">{{ item.collection || '—' }}</span></ListCell>
              <ListCell>
                <span class="text-sm tabular-nums text-ink-gray-7">{{ priceOf(item) }}</span>
                <s v-if="originalPriceOf(item)" class="ms-1.5 text-sm tabular-nums text-ink-gray-4">{{ originalPriceOf(item) }}</s>
              </ListCell>
              <ListCell>
                <span class="text-sm tabular-nums" :class="item.stock ? 'text-ink-gray-7' : 'text-ink-gray-4'">{{ item.stock || 0 }}</span>
              </ListCell>
              <ListCell>
                <div class="min-w-0 py-2">
                  <Badge :label="statusLabel(item)" :theme="statusTheme(item)" variant="subtle" />
                  <p v-if="item.issue" class="mt-1 text-p-sm text-ink-gray-6">{{ item.issue.text }}</p>
                </div>
              </ListCell>
            </ListRow>
          </ListRows>
        </List>
      </div>

      <div v-if="!filtered.length" class="py-10 text-center text-p-sm text-ink-gray-5">{{ __('No rows here.') }}</div>
    </div>
  </div>
</template>
