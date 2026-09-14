<script setup>
import { computed, ref, watch } from 'vue'
import { Avatar, TextInput } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import ListPagination from '../components/ListPagination.vue'
import ListSkeleton from '../components/ListSkeleton.vue'
import EmptyState from '../components/EmptyState.vue'
import { useAdminRead } from '../data/api'
import { longDate, money } from '../data/format'
import { useIsMobile } from '../utils/useIsMobile'
import { ia } from '../ia/store'

const query = ref('')
const page = ref(1)
const pageSize = ref(20)

const customersRequest = useAdminRead('customers.get_customers', {
  params: () => ({
    search: query.value || undefined,
    start: (page.value - 1) * pageSize.value,
    page_length: pageSize.value,
  }),
  refetch: true,
})

// A search changes what page one is, so it sends you back to it.
watch(query, () => (page.value = 1))

const total = computed(() => customersRequest.data?.total ?? 0)
const rows = computed(() => customersRequest.data?.customers ?? [])

// "Try a different search term" is a lie on a store nobody has bought from yet,
// which is the state this list is most often first seen in.
const isFiltered = computed(() => Boolean(query.value))

const isMobile = useIsMobile()

// Below `sm` the List overrides itself to two tracks and the three middle cells hide, so a
// five-cell skeleton row would spill into an implicit second grid row and draw at double
// height. Recheck this if the max-sm column override or any `max-sm:hidden` cell changes.
const skeletonColumns = computed(() => (isMobile.value ? 2 : 5))
</script>

<template>
  <!-- No header actions: a customer record is created the moment a shopper checks out
       (commera/core.py's _create_party_for_user), and there is no export endpoint. -->
  <AppPageHeader title="Customers" />

  <PageBody>
    <TextInput v-model="query" class="w-56" placeholder="Search customers" icon-left="lucide-search" />

    <div class="mt-3 overflow-x-auto">
      <!-- 46rem is the width the five columns need; a phone gets two of them instead, because
           a scroll the reader cannot see reads as a rendering fault rather than as more table.
           Spend is the number kept: it is the one that ranks customers against each other. Do
           not lower the `min-w` — below the columns' own sum the 1fr track collapses to zero
           and the customer cell disappears. -->
      <List
        class="max-sm:[--list-columns:minmax(0,1fr)_auto] sm:min-w-[46rem]"
        :row-height="Math.max(ia.density, 44)"
        :columns="['1fr', '9rem', '6rem', '8rem', '9rem']"
      >
        <ListHeader>
          <ListHeaderCell>Customer</ListHeaderCell>
          <ListHeaderCell class="max-sm:hidden">City</ListHeaderCell>
          <ListHeaderCell class="max-sm:hidden">Orders</ListHeaderCell>
          <ListHeaderCell>Spend</ListHeaderCell>
          <ListHeaderCell class="max-sm:hidden">Customer since</ListHeaderCell>
        </ListHeader>
        <!-- `loading` flips on every param change and the request keeps the previous
             `data`, so guarding on it alone would blank a loaded table on each keystroke
             in the search box. The skeleton means first load only. -->
        <ListSkeleton v-if="customersRequest.loading && !rows.length" :columns="skeletonColumns" />
        <ListRows v-else :items="rows" row-key="id" v-slot="{ item }">
          <ListRow :to="`/customers/${item.id}`" :value="item.id">
            <ListCell>
              <div class="flex min-w-0 items-center gap-2.5">
                <Avatar :label="item.name" size="sm" />
                <div class="min-w-0">
                  <p class="truncate text-base text-ink-gray-8">{{ item.name }}</p>
                  <p class="truncate text-sm text-ink-gray-5">{{ item.email ?? '—' }}</p>
                </div>
              </div>
            </ListCell>
            <ListCell class="max-sm:hidden"><span class="text-base text-ink-gray-7">{{ item.city ?? '—' }}</span></ListCell>
            <ListCell class="max-sm:hidden"><span class="text-base text-ink-gray-7 tabular-nums">{{ item.orders }}</span></ListCell>
            <ListCell><span class="text-base text-ink-gray-8 tabular-nums">{{ money(item.spend) }}</span></ListCell>
            <ListCell class="max-sm:hidden"><span class="text-base text-ink-gray-5">{{ longDate(item.since) }}</span></ListCell>
          </ListRow>
        </ListRows>
      </List>
    </div>

    <ListPagination v-if="total" v-model:page="page" v-model:page-size="pageSize" :total="total" />

    <EmptyState
      v-if="!customersRequest.loading && !rows.length"
      icon="lucide-users"
      title="No customers yet"
      description="A customer appears here the moment someone checks out."
      :filtered="isFiltered"
      filtered-title="No customers match that search"
      filtered-description="Try a different search term."
    />
  </PageBody>
</template>

