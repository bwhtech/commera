<script setup>
import { computed, ref, watch } from 'vue'
import { Button, Select, TabButtons, TextInput, toast } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListHeaderCellSort, ListRow, ListRows } from 'frappe-ui/list'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import ListPagination from '../components/ListPagination.vue'
import ResponsiveButton from '../components/ResponsiveButton.vue'
import StatusBadge from '../components/StatusBadge.vue'
import Thumb from '../components/Thumb.vue'
import EmptyState from '../components/EmptyState.vue'
import ListSkeleton from '../components/ListSkeleton.vue'
import BulkBar from '../components/BulkBar.vue'
import { useAdminRead, useAdminAction } from '../data/api'
import { pickCollectionFor, useCollections } from '../data/collections'
import { priceRange, shortDate, stockTone } from '../data/format'
import { ia } from '../ia/store'
import { openImport } from '../data/importFlow'
import { openAddProduct } from '../data/addProduct'

const STATUS_TABS = [
  { label: 'All', value: 'all' },
  { label: 'Active', value: 'active' },
  { label: 'Draft', value: 'draft' },
  { label: 'Archived', value: 'archived' },
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

const { collectionOptions: collectionPickerOptions, loading: movingToCollection, load: loadCollections } =
  useCollections()
loadCollections()

const collectionFilterOptions = computed(() => [
  { label: 'All collections', value: 'all' },
  ...collectionPickerOptions.value,
])

// Item only carries a disabled flag — there is no "draft" state in the catalog,
// so the tab stays for parity with the approved design but always reads empty.
const disabledFilter = computed(() => {
  if (status.value === 'active') return 0
  if (status.value === 'archived') return 1
  return undefined
})

const productsRequest = useAdminRead('catalog.get_products', {
  params: () => ({
    search: query.value || undefined,
    collection: collection.value !== 'all' ? collection.value : undefined,
    disabled: disabledFilter.value,
    start: (page.value - 1) * pageSize.value,
    page_length: pageSize.value,
  }),
  refetch: true,
})

// A filter changes what page one is, so it sends you back to it.
watch([query, status, collection], () => (page.value = 1))

const total = computed(() => (status.value === 'draft' ? 0 : productsRequest.data?.total ?? 0))

// The endpoint always orders by last-modified — the toggle re-sorts the
// loaded page itself, which is all a merchant is looking at when they click a header.
const rows = computed(() => {
  if (status.value === 'draft') return []
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

const archiveAction = useAdminAction('catalog.update_product')

async function archiveSelected() {
  const ids = [...selection.value]
  if (!ids.length) return

  for (const id of ids) {
    await archiveAction.submit({ item_template: id, disabled: 1 })
    // A failure already toasted inside useAdminAction — stop rather than archive the rest silently.
    if (archiveAction.error) return
  }

  toast.success(`${ids.length} product${ids.length > 1 ? 's' : ''} archived`)
  endSelecting()
  productsRequest.reload()
}

function moveToCollection() {
  const itemTemplates = [...selection.value]
  pickCollectionFor(itemTemplates, {
    label: `${itemTemplates.length} product${itemTemplates.length === 1 ? '' : 's'}`,
    onDone: () => {
      endSelecting()
      productsRequest.reload()
    },
  })
}
</script>

<template>
  <AppPageHeader title="Products">
    <template #actions>
      <ResponsiveButton label="Import" icon="lucide-upload" @click="openImport" />
      <Button label="Add product" icon-left="lucide-plus" variant="solid" theme="gray" @click="openAddProduct" />
    </template>
  </AppPageHeader>

  <PageBody>
    <div class="flex flex-wrap items-center gap-2">
      <TabButtons v-model="status" size="sm" :options="STATUS_TABS" />
      <Select v-model="collection" :options="collectionFilterOptions" />
      <TextInput
        v-model="query"
        class="ml-auto w-56"
        placeholder="Search products"
        icon-left="lucide-search"
      />
      <Button
        :label="selecting ? 'Cancel selection' : 'Select'"
        icon-left="lucide-list-checks"
        :variant="selecting ? 'solid' : 'subtle'"
        theme="gray"
        @click="selecting ? endSelecting() : (selecting = true)"
      />
    </div>

    <BulkBar v-if="selecting" :count="selection.length" noun="product" @done="endSelecting">
      <Button
        label="Move to collection"
        :loading="movingToCollection"
        @click="moveToCollection"
      />
      <Button
        label="Archive"
        theme="red"
        variant="subtle"
        :loading="archiveAction.loading"
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
          Product
        </ListHeaderCellSort>
        <ListHeaderCell>Status</ListHeaderCell>
        <ListHeaderCell>Collection</ListHeaderCell>
        <ListHeaderCellSort align="end" :direction="directionFor('stock')" @click="toggleSort('stock')">
          Inventory
        </ListHeaderCellSort>
        <ListHeaderCellSort align="end" :direction="directionFor('price')" @click="toggleSort('price')">
          Price
        </ListHeaderCellSort>
        <ListHeaderCellSort align="end" :direction="directionFor('updated')" @click="toggleSort('updated')">
          Updated
        </ListHeaderCellSort>
      </ListHeader>

      <!-- `loading` flips on every param change and the request keeps the previous
           `data`, so guarding on it alone would blank a loaded table on each sort
           toggle, keystroke and page change. The skeleton means first load only. -->
      <ListSkeleton v-if="productsRequest.loading && !rows.length" :columns="6" />

      <ListRows v-else :items="rows" row-key="name" v-slot="{ item }">
        <ListRow :to="`/products/${item.name}`" :value="item.name">
          <ListCell>
            <div class="flex min-w-0 items-center gap-2.5">
              <Thumb :image="item.image" />
              <div class="min-w-0">
                <p class="truncate text-base text-ink-gray-8">{{ item.title }}</p>
                <p class="truncate text-sm text-ink-gray-5">
                  {{ item.name }}<span v-if="item.variant_count"> · {{ item.variant_count }} variants</span>
                </p>
              </div>
            </div>
          </ListCell>
          <ListCell><StatusBadge :status="item.disabled ? 'archived' : 'active'" /></ListCell>
          <ListCell><span class="text-base text-ink-gray-7">{{ item.collection ?? '—' }}</span></ListCell>
          <ListCell>
            <span class="w-full text-right text-base tabular-nums" :class="stockTone(item.stock)">
              {{ item.stock }} in stock
            </span>
          </ListCell>
          <ListCell>
            <span class="w-full text-right text-base text-ink-gray-8 tabular-nums">
              {{ priceRange(item.price_from, item.price_to) }}
            </span>
          </ListCell>
          <ListCell>
            <span class="w-full text-right text-base text-ink-gray-5">{{ shortDate(item.updated) }}</span>
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
      title="No products yet"
      description="Add your first product, or import a catalogue to get started."
      :filtered="isFiltered"
      filtered-title="No products match"
      filtered-description="Change the filters, or import a catalogue to get started."
    >
      <Button label="Import CSV" icon-left="lucide-upload" variant="solid" theme="gray" class="mt-2" @click="openImport" />
    </EmptyState>
  </PageBody>
</template>

