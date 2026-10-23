<script setup>
import { computed } from 'vue'
import { Badge, Tooltip } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import { TabButtons } from 'frappe-ui'
import { imp } from '../../../data/importFlow'
import { money } from '../../../data/format'
import ProductThumb from '../ProductThumb.vue'
import CoachTip from '../CoachTip.vue'

const filtered = computed(() => {
  if (imp.reviewFilter === 'errors') return imp.rows.filter((r) => r.issue?.level === 'error')
  if (imp.reviewFilter === 'warnings') return imp.rows.filter((r) => r.issue?.level === 'warning')
  if (imp.reviewFilter === 'ready') return imp.rows.filter((r) => !r.issue)
  return imp.rows
})
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-xl text-ink-gray-9">Check before it goes live</h2>
      <p class="mt-1.5 text-p-base text-ink-gray-6">
        Nothing has been saved yet. Rows with an error are left out entirely; everything else imports.
      </p>
    </div>

    <div class="grid gap-4 sm:grid-cols-4">
      <div class="rounded-5 border border-outline-gray-1 p-4">
        <div class="text-2xl text-ink-gray-9 tabular-nums">{{ imp.counts.ready }}</div>
        <div class="mt-0.5 text-sm text-ink-gray-5">ready to import</div>
      </div>
      <div class="rounded-5 border border-outline-gray-1 p-4">
        <div class="text-2xl text-ink-amber-7 tabular-nums">{{ imp.counts.warnings }}</div>
        <div class="mt-0.5 text-sm text-ink-gray-5">warnings, still imported</div>
      </div>
      <div class="rounded-5 border border-outline-gray-1 p-4">
        <div class="text-2xl text-ink-red-6 tabular-nums">{{ imp.counts.errors }}</div>
        <div class="mt-0.5 text-sm text-ink-gray-5">errors, skipped</div>
      </div>
      <div class="rounded-5 border border-outline-gray-1 p-4">
        <div class="text-2xl text-ink-gray-9 tabular-nums">{{ imp.counts.products }}</div>
        <div class="mt-0.5 text-sm text-ink-gray-5">products</div>
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-3">
      <TabButtons
        v-model="imp.reviewFilter"
        :options="[
          { label: 'All rows', value: 'all' },
          { label: 'Ready', value: 'ready' },
          { label: 'Warnings', value: 'warnings' },
          { label: 'Errors', value: 'errors' },
        ]"
      />
    </div>

    <div class="overflow-hidden rounded-5 border border-outline-gray-1">
      <div class="overflow-x-auto px-2">
        <List
          class="min-w-[44rem]"
          :columns="['minmax(0,1fr)', '9rem', '7rem', '5rem', 'minmax(0,14rem)']"
          :row-height="52"
        >
          <ListHeader>
            <ListHeaderCell>Product</ListHeaderCell>
            <ListHeaderCell>Collection</ListHeaderCell>
            <ListHeaderCell>Price</ListHeaderCell>
            <ListHeaderCell>Stock</ListHeaderCell>
            <ListHeaderCell>Status</ListHeaderCell>
          </ListHeader>
          <ListRows :items="filtered" row-key="row" v-slot="{ item }">
            <ListRow :value="String(item.row)">
              <ListCell>
                <div class="flex min-w-0 items-center gap-2.5">
                  <ProductThumb :seed="`${item.title}-${item.color}`" size="size-8" icon-size="size-3.5" empty />
                  <div class="min-w-0">
                    <div class="truncate text-base text-ink-gray-8">{{ item.title || '—' }}</div>
                    <div class="truncate text-sm text-ink-gray-5">
                      {{ [item.color, item.size].filter(Boolean).join(' / ') || '—' }} · row {{ item.row }}
                    </div>
                  </div>
                </div>
              </ListCell>
              <ListCell><span class="truncate text-sm text-ink-gray-7">{{ item.collection || '—' }}</span></ListCell>
              <ListCell>
                <span class="text-sm text-ink-gray-7 tabular-nums">
                  {{ item.sale_price || item.compare_at_price ? money(item.sale_price || item.compare_at_price) : '—' }}
                </span>
              </ListCell>
              <ListCell>
                <span class="text-sm tabular-nums" :class="item.stock ? 'text-ink-gray-7' : 'text-ink-gray-4'">
                  {{ item.stock || 0 }}
                </span>
              </ListCell>
              <ListCell>
                <Badge v-if="!item.issue" label="Ready" theme="green" variant="subtle" />
                <Tooltip v-else :text="item.issue.text">
                  <div class="flex min-w-0 items-center gap-1.5">
                    <Badge
                      :label="item.issue.level === 'error' ? 'Error' : 'Warning'"
                      :theme="item.issue.level === 'error' ? 'red' : 'amber'"
                      variant="subtle"
                    />
                    <span class="truncate text-sm text-ink-gray-5">{{ item.issue.text }}</span>
                  </div>
                </Tooltip>
              </ListCell>
            </ListRow>
          </ListRows>
        </List>
      </div>

      <div v-if="!filtered.length" class="flex flex-col items-center justify-center gap-2 py-14 text-center">
        <div class="rounded-full bg-surface-green-2 p-3 text-ink-green-7">
          <span class="lucide-check size-6" aria-hidden="true" />
        </div>
        <p class="text-base text-ink-gray-7">Nothing in this bucket</p>
        <p class="text-sm text-ink-gray-5">Your file is clean on this count.</p>
      </div>

      <div v-else class="border-t border-outline-gray-1 bg-surface-gray-1 px-4 py-2.5 text-sm text-ink-gray-5">
        Showing {{ filtered.length }} of {{ imp.counts.total }} rows
      </div>
    </div>

    <CoachTip
      icon="lucide-shield-check"
      title="Errors do not stop the import"
      text="Every other row goes in — the row with the problem is simply left out, and none of its data is written."
    />
  </div>
</template>

