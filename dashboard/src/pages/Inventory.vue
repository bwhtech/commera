<script setup>
import { computed, ref } from 'vue'
import { Button, Switch, TextInput, dialog, toast } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import Thumb from '../components/Thumb.vue'
import ResponsiveButton from '../components/ResponsiveButton.vue'
import EmptyState from '../components/EmptyState.vue'
import ListSkeleton from '../components/ListSkeleton.vue'
import BulkBar from '../components/BulkBar.vue'
import { useAdminRead, useAdminAction } from '../data/api'
import { stockTone } from '../data/format'
import { ia } from '../ia/store'

const lowOnly = ref(false)
const query = ref('')
const selecting = ref(false)
const selection = ref([])

function endSelecting() {
  selecting.value = false
  selection.value = []
}

// commera is single-warehouse (Bin, resolved server-side from Commera Settings) — the mock's
// per-row `locationId` never varied, and there is no pagination control in this frozen layout
// either, so one generous page stands in for it (same call as Attributes.vue/Collections.vue).
const inventoryRequest = useAdminRead('inventory.get_inventory', {
  params: () => ({
    availability: lowOnly.value ? 'low' : undefined,
    search: query.value || undefined,
    page_length: 500,
  }),
  refetch: true,
})

const rows = computed(() => inventoryRequest.data?.rows ?? [])

// "Clear the filters" is a lie on a store with nothing stocked yet, which is the
// state this list is most often first seen in.
const isFiltered = computed(() => lowOnly.value || Boolean(query.value))

function availableStock(item) {
  return item.stock - item.committed
}

const receiveAction = useAdminAction('inventory.receive_stock')

// commera only exposes receiving stock in (Style Attribute Variant.receive_stock, additive) —
// there is no "set on-hand to X" or reason-coded adjustment endpoint, so "Adjust quantity" here
// can only mean a receipt: a dialog asks for one quantity, applied to every selected line, the
// same one-value-to-many-rows pattern VariantEditor.vue's bulk price editor already uses.
function adjust() {
  const item_codes = [...selection.value]
  if (!item_codes.length) return

  dialog.prompt({
    title: `Receive stock on ${item_codes.length} ${item_codes.length === 1 ? 'line' : 'lines'}`,
    message: 'Adds this quantity to each selected line. There is no way to set stock to an exact number here.',
    fields: [{ name: 'value', label: 'Quantity received', type: 'number', required: true }],
    onConfirm: async ({ values }) => {
      const qty = Math.max(0, Number(values.value) || 0)
      if (!qty) return

      await receiveAction.submit({
        received_quantities: Object.fromEntries(item_codes.map((code) => [code, qty])),
      })
      if (receiveAction.error) return

      endSelecting()
      toast.success(`Adjustment recorded for ${item_codes.length} lines`)
      inventoryRequest.reload()
    },
  })
}
</script>

<template>
  <AppPageHeader title="Stock">
    <template #actions>
      <!-- A real destination, so it stays reachable on a phone rather than dropping out. -->
      <ResponsiveButton label="Adjustments" icon="lucide-history" route="/inventory/adjustments" />
      <Button
        label="Receive stock"
        icon-left="lucide-plus"
        variant="solid"
        theme="gray"
        @click="selecting = true"
      />
    </template>
  </AppPageHeader>

  <PageBody>
    <div class="flex flex-wrap items-center gap-3">
      <Switch v-model="lowOnly" label="Low stock only" size="sm" />
      <TextInput v-model="query" class="ml-auto w-56" placeholder="Search SKU or product" icon-left="lucide-search" />
      <Button
        :label="selecting ? 'Cancel selection' : 'Select'"
        icon-left="lucide-list-checks"
        :variant="selecting ? 'solid' : 'subtle'"
        theme="gray"
        @click="selecting ? endSelecting() : (selecting = true)"
      />
    </div>

    <BulkBar v-if="selecting" :count="selection.length" noun="line" @done="endSelecting">
      <Button label="Adjust quantity" @click="adjust" />
    </BulkBar>

    <div class="mt-3 overflow-x-auto">
      <List
      v-model:selection="selection"
      class="min-w-[56rem]"
      :selectable="selecting"
      :row-height="Math.max(ia.density, 44)"
      :columns="['1fr', '11rem', '6rem', '6rem', '7rem']"
    >
      <ListHeader>
        <ListHeaderCell>Product</ListHeaderCell>
        <ListHeaderCell>SKU</ListHeaderCell>
        <ListHeaderCell>Committed</ListHeaderCell>
        <ListHeaderCell>Available</ListHeaderCell>
        <ListHeaderCell>On hand</ListHeaderCell>
      </ListHeader>
      <!-- `loading` flips on every param change and the request keeps the previous
           `data`, so guarding on it alone would blank a loaded table on each keystroke
           in the search box. The skeleton means first load only. -->
      <ListSkeleton v-if="inventoryRequest.loading && !rows.length" :columns="5" />
      <ListRows v-else :items="rows" row-key="item_code" v-slot="{ item }">
        <ListRow :value="item.item_code">
          <ListCell>
            <div class="flex min-w-0 items-center gap-2.5">
              <Thumb :image="item.image" size="size-7" />
              <div class="min-w-0">
                <p class="truncate text-base text-ink-gray-8">{{ item.product }}</p>
                <!-- The Available column sits off-screen in the horizontal scroller on a phone,
                     so the number this page exists for rides along on the variant line. It stays
                     on this line rather than a third one because --list-row-height is fixed. -->
                <p class="flex min-w-0 items-center text-sm text-ink-gray-5">
                  <span class="truncate">{{ item.option }} · {{ item.size }}</span>
                  <span
                    class="shrink-0 tabular-nums sm:hidden"
                    :class="stockTone(availableStock(item))"
                  >
                    &nbsp;· {{ availableStock(item) }} available
                  </span>
                </p>
              </div>
            </div>
          </ListCell>
          <ListCell><span class="truncate text-base text-ink-gray-5">{{ item.item_code }}</span></ListCell>
          <ListCell><span class="text-base text-ink-gray-5 tabular-nums">{{ item.committed }}</span></ListCell>
          <ListCell>
            <span class="text-base tabular-nums" :class="stockTone(availableStock(item))">
              {{ availableStock(item) }}
            </span>
          </ListCell>
          <ListCell>
            <!-- Read-only: this is the real on-hand number, and commera has no "set to X" write
                 for it — the only write here is the additive receive above (same convention as
                 ProductStock.vue's on-hand column). -->
            <TextInput :model-value="String(item.stock)" size="sm" class="w-16" disabled />
          </ListCell>
        </ListRow>
      </ListRows>
    </List>
    </div>

    <EmptyState
      v-if="!inventoryRequest.loading && !rows.length"
      icon="lucide-boxes"
      title="No stock yet"
      description="Add a product, then receive stock against it to see it counted here."
      :filtered="isFiltered"
      filtered-title="Nothing matches"
      filtered-description="Clear the filters to see all stock."
    />
  </PageBody>
</template>

