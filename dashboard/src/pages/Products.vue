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
import { priceRange, stockTone } from '../data/format'
import { listedVariantCount } from '../data/product'
import { useIsMobile } from '../utils/useIsMobile'
import { ia } from '../ia/store'
import { productRoute } from '../ia/routes'
import { importsLanded, openImport } from '../data/importFlow'
import { openAddProduct } from '../data/addProduct'
import {
  confirmRemoveSampleProducts,
  loadSampleProducts,
  loadSampleProductsAction,
  removeSampleProductsAction,
  sampleProductsChanged,
} from '../data/sampleProducts'
import { useBulkAction } from '../utils/useBulkAction'
import { __ } from '../data/translation'

const STATUS_TABS = [
  { label: __('All'), value: 'all' },
  { label: __('Live'), value: 'published' },
  { label: __('Draft'), value: 'unpublished' },
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

const sort = ref({ key: null, direction: 'desc' })
const page = ref(1)
const pageSize = ref(20)

const { collectionOptions: collectionPickerOptions, loading: changingCollections, load: loadCollections } =
  useCollections()
loadCollections()

const collectionFilterOptions = computed(() => [
  { label: __('All collections'), value: 'all' },
  ...collectionPickerOptions.value,
])

const disabledFilter = computed(() => (status.value === 'all' ? undefined : 0))

const publishedFilter = computed(() => {
  if (status.value === 'published') return 1
  if (status.value === 'unpublished') return 0
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

watch(importsLanded, () => productsRequest.reload())

const sampleProductsRequest = useAdminRead('sample_products.get_sample_products')
const sampleCount = computed(() => sampleProductsRequest.data?.count ?? 0)

watch(sampleProductsChanged, () => {
  productsRequest.reload()
  sampleProductsRequest.reload()
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
  if (!key) return products
  const dir = direction === 'asc' ? 1 : -1
  const valueFor = (row) => {
    if (key === 'price') return row.price_from ?? 0
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

const isMobile = useIsMobile()

// Below `sm` the List drops to two tracks and the middle cells hide, so the skeleton matches.
const skeletonColumns = computed(() => (isMobile.value ? 2 : 5))

function productStatus(product) {
  if (product.disabled) return { status: 'archived' }
  return product.published_count ? { status: 'published', label: __('Live') } : { status: 'draft', label: __('Draft') }
}

// The item code is shown only when it says something the title does not: a dashboard product is
// named after its title, so the code would repeat it.
function productSubtitle(product) {
  const variants = listedVariantCount(product)
  return [
    product.name !== product.title ? product.name : '',
    variants ? (variants === 1 ? __('1 variant') : __('{0} variants', [variants])) : '',
  ].filter(Boolean).join(' · ')
}

// A draft that never had stock is a product still being set up, not one that sold out.
function stockLabel(product) {
  if (product.stock <= 0 && !product.published_count) return { text: __('No stock yet'), tone: 'text-ink-gray-5' }
  return { text: __('{0} in stock', [product.stock]), tone: stockTone(product.stock) }
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

    <div
      v-if="sampleCount"
      class="mt-3 flex flex-wrap items-center gap-3 rounded-5 border border-outline-gray-1 bg-surface-gray-1 px-3 py-2.5"
    >
      <span class="lucide-flask-conical size-4 shrink-0 text-ink-gray-6" aria-hidden="true" />
      <p class="min-w-0 flex-1 basis-64 text-base text-ink-gray-7">
        {{ __('Demo products are in your catalogue. Remove them when you add your own.') }}
      </p>
      <Button
        :label="__('Remove demo products')"
        :loading="removeSampleProductsAction.loading"
        @click="confirmRemoveSampleProducts"
      />
    </div>

    <div class="mt-3 overflow-x-auto">
      <!-- 54rem is the width the five columns need; a phone gets two of them, because a scroll the
           reader cannot see reads as a rendering fault. Price is the one kept, and status and stock
           move under the title. Do not lower the `min-w`: below the columns' own sum the 1fr track
           collapses to zero and the product cell disappears. -->
      <List
      v-model:selection="selection"
      class="sm:min-w-[54rem]"
      :selectable="selecting"
      :row-height="Math.max(ia.density, 44)"
      :columns="{ base: ['minmax(0,1fr)', 'auto'], sm: ['1fr', '7rem', '8rem', '8rem', '7rem'] }"
    >
      <ListHeader>
        <ListHeaderCellSort :direction="directionFor('title')" @click="toggleSort('title')">
          {{ __('Product') }}
        </ListHeaderCellSort>
        <ListHeaderCell class="max-sm:hidden">{{ __('Status') }}</ListHeaderCell>
        <ListHeaderCell class="max-sm:hidden">{{ __('Collection') }}</ListHeaderCell>
        <ListHeaderCellSort
          class="max-sm:hidden"
          align="end"
          :direction="directionFor('stock')"
          @click="toggleSort('stock')"
        >
          {{ __('Inventory') }}
        </ListHeaderCellSort>
        <ListHeaderCellSort align="end" :direction="directionFor('price')" @click="toggleSort('price')">
          {{ __('Price') }}
        </ListHeaderCellSort>
      </ListHeader>

      <!-- `loading` flips on every param change and the request keeps the previous
           `data`, so guarding on it alone would blank a loaded table on each sort
           toggle, keystroke and page change. The skeleton means first load only. -->
      <ListSkeleton v-if="productsRequest.loading && !rows.length" :columns="skeletonColumns" />

      <ListRows v-else :items="rows" row-key="name" v-slot="{ item }">
        <ListRow :route="productRoute(item.name)" :value="item.name">
          <ListCell>
            <div class="flex min-w-0 items-center gap-2.5">
              <Thumb :image="item.image" />
              <div class="min-w-0">
                <p class="truncate text-base text-ink-gray-8">{{ item.title }}</p>
                <p v-if="productSubtitle(item)" class="truncate text-sm text-ink-gray-5">{{ productSubtitle(item) }}</p>
                <p class="mt-0.5 flex items-center gap-2 text-sm sm:hidden">
                  <StatusBadge v-bind="productStatus(item)" />
                  <span :class="stockLabel(item).tone">{{ stockLabel(item).text }}</span>
                </p>
              </div>
            </div>
          </ListCell>
          <ListCell class="max-sm:hidden"><StatusBadge v-bind="productStatus(item)" /></ListCell>
          <ListCell class="max-sm:hidden">
            <span class="truncate text-base text-ink-gray-7" :title="item.collections?.join(', ')">
              {{ collectionSummary(item) }}
            </span>
          </ListCell>
          <ListCell class="max-sm:hidden">
            <span class="w-full text-end text-base tabular-nums" :class="stockLabel(item).tone">
              {{ stockLabel(item).text }}
            </span>
          </ListCell>
          <ListCell>
            <span class="w-full text-end text-base text-ink-gray-8 tabular-nums">
              {{ priceRange(item.price_from, item.price_to) }}
            </span>
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
      :description="__('Add your first product, or import the ones you already sell.')"
      :filtered="isFiltered"
      :filtered-title="__('No products match')"
      :filtered-description="__('Change the filters or the search.')"
    >
      <div v-if="!isFiltered" class="mt-2 flex flex-wrap justify-center gap-2">
        <Button :label="__('Import')" icon-left="lucide-upload" @click="openImport" />
        <Button
          :label="__('Generate Demo Products')"
          icon-left="lucide-package-plus"
          :loading="loadSampleProductsAction.loading"
          @click="loadSampleProducts"
        />
        <Button :label="__('Add product')" icon-left="lucide-plus" variant="solid" theme="gray" @click="openAddProduct" />
      </div>
    </EmptyState>
  </PageBody>
</template>

