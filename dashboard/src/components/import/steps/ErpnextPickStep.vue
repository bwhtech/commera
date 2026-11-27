<script setup>
import { computed, watch } from 'vue'
import { Badge, Button, TabButtons } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import { imp } from '../../../data/importFlow'
import { loadErpnextPreview, loadErpnextSelection, previewRequest } from '../../../data/erpnextImport'
import { KIND_LABELS, selectedAfter, selectionOnPage } from '../../../data/erpnextImportState'
import { money } from '../../../data/format'
import { __ } from '../../../data/translation'
import EmptyState from '../../EmptyState.vue'
import ListPagination from '../../ListPagination.vue'
import ListSkeleton from '../../ListSkeleton.vue'
import SearchInput from '../../SearchInput.vue'
import Thumb from '../../Thumb.vue'
import CoachTip from '../CoachTip.vue'

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

function toggleAll() {
  imp.erpnext.selected = allSelected.value ? [] : [...imp.erpnext.allItemCodes]
}

const tabs = computed(() => [
  { label: __('Items ({0})', [imp.erpnext.importableCount]), value: 'items' },
  { label: __('Skipped ({0})', [imp.erpnext.skipped.length]), value: 'skipped' },
])
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-xl-semibold text-ink-gray-9">{{ __('Pick the items to bring in') }}</h2>
      <p class="mt-1.5 text-p-base text-ink-gray-6">
        {{ __('Each one becomes a draft product. Prices and stock keep coming from ERPNext, and nothing in ERPNext changes.') }}
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
        <Button
          class="ms-auto"
          variant="ghost"
          :label="allSelected ? __('Clear selection') : __('Select all')"
          :disabled="!imp.erpnext.selectionReady"
          @click="toggleAll"
        />
      </div>

      <div class="overflow-x-auto px-2">
        <List
          v-model:selection="pageSelection"
          class="min-w-[44rem]"
          selectable
          :columns="['minmax(0,1fr)', '9rem', '7rem', '5rem']"
          :row-height="52"
        >
          <ListHeader>
            <ListHeaderCell>{{ __('Item') }}</ListHeaderCell>
            <ListHeaderCell>{{ __('Options') }}</ListHeaderCell>
            <ListHeaderCell>{{ __('Price') }}</ListHeaderCell>
            <ListHeaderCell>{{ __('Stock') }}</ListHeaderCell>
          </ListHeader>
          <ListSkeleton v-if="previewRequest.loading && !imp.erpnext.items.length" :columns="4" />
          <ListRows v-else :items="imp.erpnext.items" row-key="item_code" v-slot="{ item }">
            <ListRow :value="item.item_code">
              <ListCell>
                <div class="flex min-w-0 items-center gap-2.5">
                  <Thumb :image="item.image" />
                  <div class="min-w-0">
                    <div class="truncate text-base text-ink-gray-8">{{ item.item_name }}</div>
                    <div class="truncate text-sm text-ink-gray-5">
                      {{ [item.item_code, item.item_group].filter(Boolean).join(' · ') }}
                    </div>
                  </div>
                </div>
              </ListCell>
              <ListCell>
                <Badge :label="KIND_LABELS[item.kind] ?? item.kind" theme="gray" variant="subtle" />
              </ListCell>
              <ListCell>
                <span class="text-sm text-ink-gray-7 tabular-nums">{{ item.price ? money(item.price) : '—' }}</span>
              </ListCell>
              <ListCell>
                <span class="text-sm tabular-nums" :class="item.stock ? 'text-ink-gray-7' : 'text-ink-gray-4'">
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

      <div v-else class="px-4 pb-3">
        <ListPagination
          v-model:page="imp.erpnext.page"
          v-model:page-size="imp.erpnext.pageSize"
          :total="imp.erpnext.total"
        />
      </div>
    </div>

    <div v-else class="overflow-hidden rounded-5 border border-outline-gray-1">
      <div class="overflow-x-auto px-2">
        <List class="min-w-[36rem]" :columns="['minmax(0,1fr)', 'minmax(0,16rem)']" :row-height="52">
          <ListHeader>
            <ListHeaderCell>{{ __('Item') }}</ListHeaderCell>
            <ListHeaderCell>{{ __('Why it is skipped') }}</ListHeaderCell>
          </ListHeader>
          <ListRows :items="imp.erpnext.skipped" row-key="item_code" v-slot="{ item }">
            <ListRow :value="item.item_code">
              <ListCell>
                <div class="min-w-0">
                  <div class="truncate text-base text-ink-gray-8">{{ item.item_name }}</div>
                  <div class="truncate text-sm text-ink-gray-5">{{ item.item_code }}</div>
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
