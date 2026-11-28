<script setup>
import { computed, watch } from 'vue'
import { Badge, Button, Checkbox, Skeleton, TabButtons } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import { imp } from '../../../data/importFlow'
import { loadErpnextPreview, loadErpnextSelection, previewRequest } from '../../../data/erpnextImport'
import {
  KIND_LABELS,
  isEveryShownSelected,
  selectedAfter,
  selectionOnPage,
  toggledSelection,
} from '../../../data/erpnextImportState'
import { money } from '../../../data/format'
import { __ } from '../../../data/translation'
import { useIsMobile } from '../../../utils/useIsMobile'
import EmptyState from '../../EmptyState.vue'
import ListPagination from '../../ListPagination.vue'
import ListSkeleton from '../../ListSkeleton.vue'
import SearchInput from '../../SearchInput.vue'
import Thumb from '../../Thumb.vue'
import CoachTip from '../CoachTip.vue'
import DotList from '../../DotList.vue'

const isMobile = useIsMobile()

loadErpnextSelection()
loadErpnextPreview()

watch(
  () => imp.erpnext.search,
  () => {
    imp.erpnext.page = 1
    loadErpnextPreview()
  },
)
watch(() => [imp.erpnext.page, imp.erpnext.pageSize], loadErpnextPreview)

const pageSelection = computed({
  get: () => selectionOnPage(imp.erpnext.items, imp.erpnext.selected),
  set: (selection) => (imp.erpnext.selected = selectedAfter(imp.erpnext.items, selection, imp.erpnext.selected)),
})

const allSelected = computed(() => imp.erpnext.selected.length === imp.erpnext.importableCount)

function toggleItem(itemCode, isSelected) {
  const others = imp.erpnext.selected.filter((code) => code !== itemCode)
  imp.erpnext.selected = isSelected ? [...others, itemCode] : others
}

const kindLabel = (item) => KIND_LABELS[item.kind] ?? item.kind

// A plain item has no options to name: "No options" on every row of a plain catalog is noise. The
// kind shows only on an item that has some, and the Options column only while one is on the page.
const hasOptions = (item) => item.kind !== 'plain'
const showsOptions = computed(() => imp.erpnext.items.some(hasOptions))
const pickColumns = computed(() =>
  showsOptions.value ? ['minmax(0,1fr)', '9rem', '7rem', '5rem'] : ['minmax(0,1fr)', '7rem', '5rem'],
)

const factsOf = (item) => [
  hasOptions(item) && kindLabel(item),
  item.price
    ? { label: money(item.price), class: 'tabular-nums text-ink-gray-7' }
    : { label: __('No price yet'), class: 'text-ink-amber-8' },
  { label: __('{0} in stock', [item.stock || 0]), class: 'tabular-nums' },
].filter(Boolean)

// Items made in Desk are named after their code by default, and "Bowl / Bowl · Products" says the
// name twice. The code shows only when it tells the seller something the name does not.
const subtitleOf = (item) =>
  [item.item_code !== item.item_name && item.item_code, item.item_group].filter(Boolean).join(' · ')
const skippedSubtitleOf = (item) => (item.item_code !== item.item_name ? item.item_code : '')

const isSearching = computed(() => Boolean(imp.erpnext.search))
const shownCodes = computed(() => imp.erpnext.items.map((item) => item.item_code))
const isShowingCurrentSearch = computed(() => imp.erpnext.itemsSearch === (imp.erpnext.search || ''))

const toggleLabel = computed(() => {
  if (!isSearching.value) return allSelected.value ? __('Clear selection') : __('Select all')
  const shown = shownCodes.value.length
  return isEveryShownSelected(imp.erpnext.selected, shownCodes.value)
    ? __('Clear {0} shown', [shown])
    : __('Select {0} shown', [shown])
})

function toggleAll() {
  imp.erpnext.selected = toggledSelection({
    selected: imp.erpnext.selected,
    allCodes: imp.erpnext.allItemCodes,
    shownCodes: shownCodes.value,
    isSearching: isSearching.value,
  })
}

// While a search is on, the tab says how much of the list it shows, so "3 of 9 selected" beside three
// rows does not read as a miscount.
const itemsTabLabel = computed(() => {
  if (isSearching.value && isShowingCurrentSearch.value) {
    return __('Items ({0} of {1})', [imp.erpnext.total, imp.erpnext.importableCount])
  }
  return __('Items ({0})', [imp.erpnext.importableCount])
})

// One page holds everything: "1–6 of 6" and two disabled buttons are chrome with nothing to do.
const hasMorePages = computed(() => imp.erpnext.total > imp.erpnext.pageSize || imp.erpnext.page > 1)

const tabs = computed(() => [
  { label: itemsTabLabel.value, value: 'items' },
  { label: __('Skipped ({0})', [imp.erpnext.skipped.length]), value: 'skipped' },
])
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-lg-semibold text-ink-gray-9">{{ __('Pick the items to bring in') }}</h2>
      <p class="mt-1.5 text-p-base text-ink-gray-6">
        {{ __('Each one becomes a product that is not published yet. Prices and stock keep coming from ERPNext, and nothing in ERPNext changes.') }}
      </p>
    </div>

    <div class="flex flex-wrap items-center gap-3">
      <TabButtons v-model="imp.erpnext.tab" :options="tabs" />
      <SearchInput
        v-if="imp.erpnext.tab === 'items'"
        v-model="imp.erpnext.search"
        class="min-w-0 flex-1 basis-40 sm:ms-auto sm:w-56 sm:flex-none sm:basis-auto"
        :placeholder="__('Search items')"
      />
    </div>

    <div v-if="imp.erpnext.tab === 'items'" class="overflow-hidden rounded-5 border border-outline-gray-1">
      <div class="flex items-center gap-3 border-b border-outline-gray-1 bg-surface-gray-1 px-4 py-2.5">
        <span class="text-sm text-ink-gray-6 tabular-nums">
          {{ __('{0} of {1} selected', [imp.erpnext.selected.length, imp.erpnext.importableCount]) }}
        </span>
        <!-- Disabled while a search loads: the rows on screen still belong to the previous search, so
             "Select N shown" would pick items the new search hides. -->
        <Button
          v-if="!isSearching || shownCodes.length"
          class="ms-auto"
          variant="ghost"
          :label="toggleLabel"
          :disabled="!imp.erpnext.selectionReady || !isShowingCurrentSearch"
          @click="toggleAll"
        />
      </div>

      <!-- Below sm each item is a stacked row: the four columns cannot share 390px, and a sideways
           scroll hid the price and stock a seller needs before picking. -->
      <div v-if="isMobile" class="divide-y divide-outline-gray-1">
        <template v-if="previewRequest.loading && !imp.erpnext.items.length">
          <div v-for="row in 4" :key="row" class="px-4 py-4" aria-hidden="true">
            <Skeleton class="h-3.5 w-40 rounded-4" />
          </div>
        </template>
        <template v-else>
          <label v-for="item in imp.erpnext.items" :key="item.item_code" class="flex items-start gap-3 px-4 py-3">
            <Checkbox
              class="mt-2.5"
              :model-value="imp.erpnext.selected.includes(item.item_code)"
              :aria-label="__('Import {0}', [item.item_name])"
              @update:model-value="(isSelected) => toggleItem(item.item_code, isSelected)"
            />
            <Thumb :image="item.image" />
            <div class="min-w-0 flex-1">
              <div class="truncate text-base text-ink-gray-8">{{ item.item_name }}</div>
              <DotList class="mt-0.5 text-sm text-ink-gray-6" :parts="factsOf(item)" />
            </div>
          </label>
        </template>
      </div>

      <!-- list-row-px-2 gives the header the same inset as the selectable rows (frappe-ui pads only
           clickable rows by default, which put every header label 12px off its column), and with the
           px-2 wrapper the checkboxes sit 16px in, under the px-4 selection bar above. -->
      <div v-else class="px-2">
        <List
          v-model:selection="pageSelection"
          class="list-row-px-2"
          selectable
          :columns="pickColumns"
          :row-height="52"
        >
          <!-- Price and Stock end-align, header included, like every number column in the product flows. -->
          <ListHeader class="text-ink-gray-6">
            <ListHeaderCell>{{ __('Item') }}</ListHeaderCell>
            <ListHeaderCell v-if="showsOptions">{{ __('Options') }}</ListHeaderCell>
            <ListHeaderCell class="justify-end">{{ __('Price') }}</ListHeaderCell>
            <ListHeaderCell class="justify-end">{{ __('Stock') }}</ListHeaderCell>
          </ListHeader>
          <ListSkeleton v-if="previewRequest.loading && !imp.erpnext.items.length" :columns="pickColumns.length" />
          <ListRows v-else :items="imp.erpnext.items" row-key="item_code" v-slot="{ item }">
            <ListRow :value="item.item_code">
              <ListCell>
                <div class="flex min-w-0 items-center gap-2.5">
                  <Thumb :image="item.image" />
                  <div class="min-w-0">
                    <div class="truncate text-base text-ink-gray-8">{{ item.item_name }}</div>
                    <div v-if="subtitleOf(item)" class="truncate text-sm text-ink-gray-6">{{ subtitleOf(item) }}</div>
                  </div>
                </div>
              </ListCell>
              <ListCell v-if="showsOptions">
                <Badge v-if="hasOptions(item)" :label="kindLabel(item)" theme="gray" variant="subtle" />
              </ListCell>
              <ListCell class="justify-end">
                <span v-if="item.price" class="text-sm text-ink-gray-7 tabular-nums">{{ money(item.price) }}</span>
                <span v-else class="text-sm text-ink-amber-8">{{ __('No price yet') }}</span>
              </ListCell>
              <ListCell class="justify-end">
                <span class="text-sm tabular-nums" :class="item.stock ? 'text-ink-gray-7' : 'text-ink-gray-6'">
                  {{ item.stock || 0 }}
                </span>
              </ListCell>
            </ListRow>
          </ListRows>
        </List>
      </div>

      <EmptyState
        v-if="!previewRequest.loading && !imp.erpnext.items.length"
        compact
        icon="lucide-package"
        :title="__('No items to import')"
        :description="__('Every sales item in ERPNext is already a product.')"
        :filtered="Boolean(imp.erpnext.search)"
        :filtered-title="__('No items match')"
        :filtered-description="__('Try another name or item code.')"
      />

      <div v-else-if="hasMorePages" class="px-4 pb-3">
        <ListPagination
          v-model:page="imp.erpnext.page"
          v-model:page-size="imp.erpnext.pageSize"
          :total="imp.erpnext.total"
        />
      </div>
    </div>

    <div v-else class="overflow-hidden rounded-5 border border-outline-gray-1">
      <div v-if="isMobile" class="divide-y divide-outline-gray-1">
        <div v-for="item in imp.erpnext.skipped" :key="item.item_code" class="px-4 py-3">
          <div class="truncate text-base text-ink-gray-8">{{ item.item_name }}</div>
          <p class="mt-0.5 text-p-sm text-ink-gray-6">{{ item.reason }}</p>
        </div>
      </div>
      <div v-else class="px-2">
        <List class="list-row-px-2" :columns="['minmax(0,1fr)', 'minmax(0,16rem)']" :row-height="52">
          <ListHeader class="text-ink-gray-6">
            <ListHeaderCell>{{ __('Item') }}</ListHeaderCell>
            <ListHeaderCell>{{ __('Why it is skipped') }}</ListHeaderCell>
          </ListHeader>
          <ListRows :items="imp.erpnext.skipped" row-key="item_code" v-slot="{ item }">
            <ListRow :value="item.item_code">
              <ListCell>
                <div class="min-w-0">
                  <div class="truncate text-base text-ink-gray-8">{{ item.item_name }}</div>
                  <div v-if="skippedSubtitleOf(item)" class="truncate text-sm text-ink-gray-6">{{ skippedSubtitleOf(item) }}</div>
                </div>
              </ListCell>
              <ListCell><span class="truncate text-sm text-ink-gray-6">{{ item.reason }}</span></ListCell>
            </ListRow>
          </ListRows>
        </List>
      </div>

      <EmptyState
        v-if="!imp.erpnext.skipped.length"
        compact
        icon="lucide-check"
        :title="__('Nothing skipped')"
        :description="__('Every item ERPNext sells can come across.')"
      />
    </div>

    <CoachTip
      icon="lucide-shield-check"
      :title="__('Safe to run again')"
      :text="__('Items that are already products are left alone, so a second run only brings in what is new.')"
    />
  </div>
</template>
