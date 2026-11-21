<script setup>
import { computed, ref, watch } from 'vue'
import { Button, Select, toast } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListHeaderCellSort, ListRow, ListRows } from 'frappe-ui/list'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import ListTabs from '../components/ListTabs.vue'
import ListPagination from '../components/ListPagination.vue'
import ResponsiveButton from '../components/ResponsiveButton.vue'
import StatusBadge from '../components/StatusBadge.vue'
import Thumb from '../components/Thumb.vue'
import EmptyState from '../components/EmptyState.vue'
import ListSkeleton from '../components/ListSkeleton.vue'
import BulkBar from '../components/BulkBar.vue'
import SearchInput from '../components/SearchInput.vue'
import { useAdminRead, useAdminAction } from '../data/api'
import { pickCollectionFor, useCollections } from '../data/collections'
import { priceRange, shortDate, stockTone } from '../data/format'
import { ia } from '../ia/store'
import { productRoute } from '../ia/routes'
import { openImport } from '../data/importFlow'
import { openAddProduct } from '../data/addProduct'
import { useBulkAction } from '../utils/useBulkAction'
import { __ } from '../data/translation'

const STATUS_TABS = [
  { label: __('All'), value: 'all' },
  { label: __('Active'), value: 'active' },
  { label: __('Draft'), value: 'draft' },
  { label: __('Archived'), value: 'archived' },
]

const status = ref('all')
const collection = ref('all')
const query = ref('')
const selecting = ref(false)
const selection = ref([])

function endSelecting() {
  selecting.value = false
  selection.value = []
}

const sort = ref({ key: 'updated', direction: 'desc' })
const page = ref(1)
const pageSize = ref(20)

const { collectionOptions: collectionPickerOptions, loading: changingCollections, load: loadCollections } =
  useCollections()
loadCollections()

const collectionFilterOptions = computed(() => [
  { label: __('All collections'), value: 'all' },
  ...collectionPickerOptions.value,
])

const disabledFilter = computed(() => {
  if (status.value === 'active' || status.value === 'draft') return 0
  if (status.value === 'archived') return 1
  return undefined
})

const publishedFilter = computed(() => {
  if (status.value === 'active') return 1
  if (status.value === 'draft') return 0
  return undefined
})

const productsRequest = useAdminRead('catalog.get_products', {
  params: () => ({
    search: query.value || undefined,
    collection: collection.value !== 'all' ? collection.value : undefined,
    disabled: disabledFilter.value,
    published: publishedFilter.value,
    start: (page.value - 1) * pageSize.value,
    page_length: pageSize.value,
  }),
  refetch: true,
})

// A filter changes what page one is, so it sends you back to it.
watch([query, status, collection], () => (page.value = 1))

// Bumped when the list changes under a bulk run, so the run does not restore a selection from the old list.
let listView = 0

// A selection only means the rows on screen: archiving products the merchant can no longer see
// is a surprise.
watch([query, status, collection, page, pageSize], () => {
  listView += 1
  selection.value = []
})

const total = computed(() => productsRequest.data?.total ?? 0)

// The endpoint always orders by last-modified — the toggle re-sorts the
// loaded page itself, which is all a merchant is looking at when they click a header.
const rows = computed(() => {
  const products = productsRequest.data?.products ?? []
  const { key, direction } = sort.value
  const dir = direction === 'asc' ? 1 : -1
  const valueFor = (row) => {
    if (key === 'price') return row.price_from ?? 0
    if (key === 'updated') return row.updated
    if (key === 'title') return row.title
    return row.stock
  }
  return [...products].sort((a, b) => {
    const av = valueFor(a)
    const bv = valueFor(b)
    return av > bv ? dir : av < bv ? -dir : 0
  })
})

// A reload can move a selected row off this page (an archive, a new order): keep only the rows shown.
watch(
  () => productsRequest.data,
  (data) => {
    if (!data) return
    const shown = new Set(rows.value.map((row) => row.name))
    const kept = selection.value.filter((name) => shown.has(name))
    if (kept.length !== selection.value.length) selection.value = kept
  },
)

// "Change the filters" is a lie on a store with an empty catalogue, which is the
// state this list is most often first seen in.
const isFiltered = computed(
  () => Boolean(query.value) || status.value !== 'all' || collection.value !== 'all',
)

function toggleSort(key) {
  sort.value =
    sort.value.key === key
      ? { key, direction: sort.value.direction === 'asc' ? 'desc' : 'asc' }
      : { key, direction: 'asc' }
}

const directionFor = (key) => (sort.value.key === key ? sort.value.direction : null)

const archiveAction = useAdminAction('catalog.update_product', { quiet: true })
const { running: bulkRunning, run: runBulk } = useBulkAction()

async function archiveSelected() {
  const view = listView
  await runBulk('Archive', [...selection.value], (id) => archiveAction.submit({ item_template: id, disabled: 1 }), {
    sentences: {
      all: (count) => (count === 1 ? __('1 product archived') : __('{0} products archived', [count])),
      some: (done, total, failed) => __('{0} of {1} products archived. {2} failed', [done, total, failed]),
    },
    after: ({ failed }) => {
      if (view === listView) {
        selection.value = failed.map(({ item }) => item)
        if (!failed.length) endSelecting()
      }
      return productsRequest.reload()
    },
  })
}

function changeCollection(mode) {
  const itemTemplates = [...selection.value]
  pickCollectionFor(itemTemplates, {
    label: itemTemplates.length === 1 ? __('1 product') : __('{0} products', [itemTemplates.length]),
    mode,
    onDone: () => {
      endSelecting()
      productsRequest.reload()
    },
  })
}

function collectionSummary(product) {
  const others = (product.collections?.length ?? 1) - 1
  return others > 0 ? `${product.collection} +${others}` : (product.collection ?? '—')
}
</script>

<template>
  <AppPageHeader :title="__('Products')">
    <template #actions>
      <ResponsiveButton :label="__('Import')" icon="lucide-upload" @click="openImport" />
      <Button :label="__('Add product')" icon-left="lucide-plus" variant="solid" theme="gray" @click="openAddProduct" />
    </template>
  </AppPageHeader>

  <PageBody>
    <div class="flex flex-wrap items-center gap-2">
      <ListTabs v-model="status" :options="STATUS_TABS" />
      <Select v-model="collection" :options="collectionFilterOptions" />
      <SearchInput
        v-model="query"
        class="min-w-0 flex-1 basis-40 sm:ms-auto sm:w-56 sm:flex-none sm:basis-auto"
        :placeholder="__('Search products')"
      />
      <ResponsiveButton
        :label="selecting ? __('Cancel selection') : __('Select')"
        icon="lucide-list-checks"
        :variant="selecting ? 'solid' : 'subtle'"
        theme="gray"
        @click="selecting ? endSelecting() : (selecting = true)"
      />
    </div>

    <BulkBar
      v-if="selecting"
      :count="selection.length"
      :selected-label="selection.length === 1 ? __('1 product selected') : __('{0} products selected', [selection.length])"
      :empty-label="__('Select products to act on them')"
      :busy="Boolean(bulkRunning) || changingCollections"
      @done="endSelecting"
    >
      <Button :label="__('Add to collection')" :loading="changingCollections" @click="changeCollection('add')" />
      <Button
        :label="__('Remove from collection')"
        :loading="changingCollections"
        @click="changeCollection('remove')"
      />
      <Button
        :label="__('Archive')"
        theme="red"
        variant="subtle"
        :loading="bulkRunning === 'Archive'"
        @click="archiveSelected"
      />
    </BulkBar>

    <div class="mt-3 overflow-x-auto">
      <List
      v-model:selection="selection"
      class="min-w-[54rem]"
      :selectable="selecting"
      :row-height="ia.density"
      :columns="['1fr', '7rem', '8rem', '8rem', '7rem', '6rem']"
    >
      <ListHeader>
        <ListHeaderCellSort :direction="directionFor('title')" @click="toggleSort('title')">
          {{ __('Product') }}
        </ListHeaderCellSort>
        <ListHeaderCell>{{ __('Status') }}</ListHeaderCell>
        <ListHeaderCell>{{ __('Collection') }}</ListHeaderCell>
        <ListHeaderCellSort align="end" :direction="directionFor('stock')" @click="toggleSort('stock')">
          {{ __('Inventory') }}
        </ListHeaderCellSort>
        <ListHeaderCellSort align="end" :direction="directionFor('price')" @click="toggleSort('price')">
          {{ __('Price') }}
        </ListHeaderCellSort>
        <ListHeaderCellSort align="end" :direction="directionFor('updated')" @click="toggleSort('updated')">
          {{ __('Updated', null, 'Date last updated') }}
        </ListHeaderCellSort>
      </ListHeader>

      <!-- `loading` flips on every param change and the request keeps the previous
           `data`, so guarding on it alone would blank a loaded table on each sort
           toggle, keystroke and page change. The skeleton means first load only. -->
      <ListSkeleton v-if="productsRequest.loading && !rows.length" :columns="6" />

      <ListRows v-else :items="rows" row-key="name" v-slot="{ item }">
        <ListRow :route="productRoute(item.name)" :value="item.name">
          <ListCell>
            <div class="flex min-w-0 items-center gap-2.5">
              <Thumb :image="item.image" />
              <div class="min-w-0">
                <p class="truncate text-base text-ink-gray-8">{{ item.title }}</p>
                <p class="truncate text-sm text-ink-gray-5">
                  {{ item.name }}<span v-if="item.variant_count"> · {{ __('{0} variants', [item.variant_count]) }}</span>
                </p>
              </div>
            </div>
          </ListCell>
          <ListCell><StatusBadge :status="item.disabled ? 'archived' : item.published_count ? 'active' : 'draft'" /></ListCell>
          <ListCell>
            <span class="truncate text-base text-ink-gray-7" :title="item.collections?.join(', ')">
              {{ collectionSummary(item) }}
            </span>
          </ListCell>
          <ListCell>
            <span class="w-full text-end text-base tabular-nums" :class="stockTone(item.stock)">
              {{ __('{0} in stock', [item.stock]) }}
            </span>
          </ListCell>
          <ListCell>
            <span class="w-full text-end text-base text-ink-gray-8 tabular-nums">
              {{ priceRange(item.price_from, item.price_to) }}
            </span>
          </ListCell>
          <ListCell>
            <span class="w-full text-end text-base text-ink-gray-5">{{ shortDate(item.updated) }}</span>
          </ListCell>
        </ListRow>
      </ListRows>
    </List>
    </div>

    <ListPagination
      v-if="total"
      v-model:page="page"
      v-model:page-size="pageSize"
      :total="total"
    />

    <EmptyState
      v-if="!productsRequest.loading && !rows.length"
      icon="lucide-package"
      :title="__('No products yet')"
      :description="__('Add your first product, or import a catalogue to get started.')"
      :filtered="isFiltered"
      :filtered-title="__('No products match')"
      :filtered-description="__('Change the filters, or import a catalogue to get started.')"
    >
      <Button :label="__('Import CSV')" icon-left="lucide-upload" variant="solid" theme="gray" class="mt-2" @click="openImport" />
    </EmptyState>
  </PageBody>
</template>

