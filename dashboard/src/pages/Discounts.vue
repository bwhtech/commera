<script setup>
import { computed, ref, watch } from 'vue'
import { Badge, Button, TabButtons, TextInput } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import EmptyState from '../components/EmptyState.vue'
import ListPagination from '../components/ListPagination.vue'
import ListSkeleton from '../components/ListSkeleton.vue'
import DiscountTypeDialog from '../components/discounts/DiscountTypeDialog.vue'
import { STATUS_THEMES, discountTypeByValue, summaryLines } from '../data/discounts'
import { useAdminRead } from '../data/api'
import { money } from '../data/format'
import { ia } from '../ia/store'
import { useIsMobile } from '../utils/useIsMobile'

const TABS = [
  { label: 'All', value: 'all' },
  { label: 'Active', value: 'active' },
  { label: 'Scheduled', value: 'scheduled' },
  { label: 'Expired', value: 'expired' },
]

const tab = ref('all')
const query = ref('')
const page = ref(1)
const pageSize = ref(20)
const creating = ref(false)

const discountsRequest = useAdminRead('discounts.get_discounts', {
  params: () => ({
    tab: tab.value,
    search: query.value || undefined,
    start: (page.value - 1) * pageSize.value,
    page_length: pageSize.value,
  }),
  refetch: true,
})

// A new tab or search changes what page one is, so it sends you back to it.
watch([tab, query], () => (page.value = 1))

const rows = computed(() => discountsRequest.data?.discounts ?? [])
const total = computed(() => discountsRequest.data?.total ?? 0)
const isMobile = useIsMobile()

function heading(row) {
  if (row.method === 'Automatic') return row.title
  if (row.code) return row.code
  return `${row.generated_codes} unique codes`
}

function usage(row) {
  return row.usage_limit ? `${row.times_used} / ${row.usage_limit}` : String(row.times_used)
}
</script>

<template>
  <AppPageHeader title="Discounts">
    <template #actions>
      <Button label="Create discount" variant="solid" theme="gray" icon-left="lucide-plus" @click="creating = true" />
    </template>
  </AppPageHeader>

  <PageBody>
    <div class="flex flex-wrap items-center gap-2">
      <TabButtons v-model="tab" size="sm" :options="TABS" />
      <TextInput v-model="query" class="w-56" placeholder="Search titles and codes" icon-left="lucide-search" :debounce="300" />
    </div>

    <div class="mt-3 overflow-x-auto">
      <!-- 52rem fits the six columns; a phone keeps the discount and its status. Do not lower the
           min-w: below the columns' own sum the 1fr track collapses and the discount cell vanishes. -->
      <List
        class="max-sm:[--list-columns:minmax(0,1fr)_auto] sm:min-w-[52rem]"
        :row-height="Math.max(ia.density, 56)"
        :columns="['1fr', '9rem', '7rem', '6rem', '8rem', '6rem']"
      >
        <ListHeader>
          <ListHeaderCell>Discount</ListHeaderCell>
          <ListHeaderCell class="max-sm:hidden">Type</ListHeaderCell>
          <ListHeaderCell class="max-sm:hidden">Method</ListHeaderCell>
          <ListHeaderCell class="max-sm:hidden">Used</ListHeaderCell>
          <ListHeaderCell class="max-sm:hidden">Discount given</ListHeaderCell>
          <ListHeaderCell>Status</ListHeaderCell>
        </ListHeader>
        <ListSkeleton v-if="discountsRequest.loading && !rows.length" :columns="isMobile ? 2 : 6" />
        <ListRows v-else :items="rows" row-key="name" v-slot="{ item }">
          <ListRow :to="{ name: 'DiscountDetail', params: { id: item.name } }" :value="item.name">
            <ListCell>
              <div class="min-w-0">
                <p class="truncate text-base-medium text-ink-gray-8">{{ heading(item) }}</p>
                <p class="truncate text-sm text-ink-gray-5">{{ summaryLines(item).slice(0, 2).join(' · ') }}</p>
              </div>
            </ListCell>
            <ListCell class="max-sm:hidden">
              <span class="text-base text-ink-gray-7">{{ discountTypeByValue[item.discount_type].label }}</span>
            </ListCell>
            <ListCell class="max-sm:hidden"><span class="text-base text-ink-gray-7">{{ item.method }}</span></ListCell>
            <ListCell class="max-sm:hidden"><span class="text-base tabular-nums text-ink-gray-7">{{ usage(item) }}</span></ListCell>
            <ListCell class="max-sm:hidden">
              <span class="text-base tabular-nums text-ink-gray-7">{{ money(item.discount_given) }}</span>
            </ListCell>
            <ListCell><Badge :label="item.status" :theme="STATUS_THEMES[item.status]" variant="subtle" /></ListCell>
          </ListRow>
        </ListRows>
      </List>
    </div>

    <ListPagination v-if="total" v-model:page="page" v-model:page-size="pageSize" :total="total" />

    <EmptyState
      v-if="!discountsRequest.loading && !rows.length"
      icon="lucide-badge-percent"
      title="No discounts yet"
      description="Create a code shoppers type at checkout, or a discount that applies on its own."
      :filtered="Boolean(query) || tab !== 'all'"
      filtered-title="No discounts match"
      filtered-description="Try another tab or search."
    />
  </PageBody>

  <DiscountTypeDialog v-model:open="creating" />
</template>
