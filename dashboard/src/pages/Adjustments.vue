<script setup>
import { computed } from 'vue'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import EmptyState from '../components/EmptyState.vue'
import ListSkeleton from '../components/ListSkeleton.vue'
import { useAdminRead } from '../data/api'
import { shortDate } from '../data/format'
import { ia } from '../ia/store'

// commera keeps no adjustment-with-reason ledger of its own — the only stock write anywhere in
// the app is Style Attribute Variant.receive_stock (additive-only, see Inventory.vue). Rather
// than fake a ledger, this reads the real one ERPNext already keeps for every stock-affecting
// document (Stock Ledger Entry) against the shop's own warehouse. In this dataset every row so
// far is a receipt, because nothing else has posted against the warehouse yet — the endpoint's
// reason mapping also covers sales/issues/counts once those exist, it isn't Received-only by design.
const movementsRequest = useAdminRead('inventory.get_stock_movements', {
  params: () => ({ page_length: 200 }),
})

const rows = computed(() => movementsRequest.data?.rows ?? [])
</script>

<template>
  <AppPageHeader title="Adjustments" back-to="/inventory" />

  <PageBody>
    <p class="text-p-sm text-ink-gray-5">Every stock movement, in order. Read-only.</p>

    <div class="mt-3 overflow-x-auto">
      <List class="min-w-[52rem]" :row-height="ia.density" :columns="['7rem', '1fr', '11rem', '6rem', '9rem', '7rem']">
      <ListHeader>
        <ListHeaderCell>Date</ListHeaderCell>
        <ListHeaderCell>Product</ListHeaderCell>
        <ListHeaderCell>SKU</ListHeaderCell>
        <ListHeaderCell>Change</ListHeaderCell>
        <ListHeaderCell>Reason</ListHeaderCell>
        <ListHeaderCell>By</ListHeaderCell>
      </ListHeader>
      <!-- `loading` flips on every reload and the request keeps the previous `data`,
           so guarding on it alone would blank a loaded table on a refetch. The
           skeleton means first load only. -->
      <ListSkeleton v-if="movementsRequest.loading && !rows.length" :columns="6" />
      <ListRows v-else :items="rows" row-key="name" v-slot="{ item }">
        <ListRow :value="item.name">
          <ListCell><span class="text-base text-ink-gray-5">{{ shortDate(item.date) }}</span></ListCell>
          <ListCell><span class="truncate text-base text-ink-gray-8">{{ item.product }}</span></ListCell>
          <ListCell><span class="truncate text-base text-ink-gray-5">{{ item.sku }}</span></ListCell>
          <ListCell>
            <span class="text-base tabular-nums" :class="item.delta > 0 ? 'text-ink-green-6' : 'text-ink-red-6'">
              {{ item.delta > 0 ? '+' : '' }}{{ item.delta }}
            </span>
          </ListCell>
          <ListCell><span class="text-base text-ink-gray-7">{{ item.reason }}</span></ListCell>
          <ListCell><span class="text-base text-ink-gray-5">{{ item.by }}</span></ListCell>
        </ListRow>
      </ListRows>
    </List>
    </div>

    <EmptyState v-if="!movementsRequest.loading && !rows.length" icon="lucide-history" title="No movements yet" description="Stock receipts and sales will show up here." />
  </PageBody>
</template>
