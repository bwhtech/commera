<script setup>
import { computed, ref } from 'vue'
import { Badge, Button, Skeleton } from 'frappe-ui'
import { BarChart, LineChart } from 'frappe-ui/charts'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import ReportHeader from '../../components/ReportHeader.vue'
import ReportStats from '../../components/ReportStats.vue'
import PageBody from '../../components/PageBody.vue'
import EmptyState from '../../components/EmptyState.vue'
import ListSkeleton from '../../components/ListSkeleton.vue'
import { useAdminRead } from '../../data/api'
import { hasValues, monthsForRange } from '../../data/analytics'
import { compactMoney, money } from '../../data/format'
import { ia } from '../../ia/store'

const range = ref('Last 12 months')
const compare = ref(true)

const reportRequest = useAdminRead('analytics.get_inventory_report', {
  params: () => ({ months: monthsForRange(range.value) }),
  refetch: true,
})

const report = computed(() => reportRequest.data)
const stockValueByMonth = computed(() => report.value?.stock_value_by_month ?? [])
const velocity = computed(() => report.value?.velocity ?? [])
const deadStock = computed(() => report.value?.dead_stock ?? [])

// This report carries no "previous period" comparison for stock levels — a snapshot ("what's on
// the shelf right now") has no natural prior-window baseline the way a revenue total does, so the
// compare toggle simply has nothing to show for these four tiles.
const stats = computed(() => {
  const stat = report.value?.stats ?? {}
  return [
    { label: 'Stock value', value: compactMoney(stat.stock_value?.value ?? 0), delta: null, up: true },
    { label: 'Units on hand', value: (stat.units_on_hand?.value ?? 0).toLocaleString('en-IN'), delta: null, up: true },
    {
      label: 'Days of cover',
      value: stat.days_of_cover?.value != null ? String(stat.days_of_cover.value) : '—',
      delta: null,
      up: true,
    },
    { label: 'Capital in dead stock', value: compactMoney(stat.dead_stock_value?.value ?? 0), delta: null, up: false },
  ]
})

// Both velocity panels read the same series, but they measure different things — a sell-through of
// zero is "nothing has sold", a cover of zero is "there is no pace to project from" — so each says
// why its own bars are missing.
const noSellThroughState = {
  icon: 'lucide-chart-column',
  title: 'No movement yet',
  description: 'Stock movement appears once products start selling.',
}
const noCoverState = {
  icon: 'lucide-timer',
  title: 'No sales pace yet',
  description: 'Days of cover needs recent sales to project from.',
}
</script>

<template>
  <ReportHeader title="Inventory" v-model:range="range" v-model:compare="compare" />

  <PageBody width="narrow">
    <div>
      <h1 class="text-2xl text-ink-gray-9">Inventory</h1>
      <p class="mt-1 text-p-base text-ink-gray-6">
        How much capital the shelves are holding, and how fast it turns. {{ range }}.
      </p>
    </div>

    <ReportStats
      class="mt-5"
      :stats="stats"
      :compare="compare"
      :loading="reportRequest.loading && !report"
    />

    <section class="mt-6 rounded-5 border border-outline-gray-1 p-4">
      <h2 class="text-lg-semibold text-ink-gray-8">Stock value over time</h2>
      <Skeleton v-if="reportRequest.loading && !stockValueByMonth.length" class="h-72 w-full rounded" />
      <EmptyState
        v-else-if="!hasValues(stockValueByMonth, 'value')"
        compact
        icon="lucide-chart-line"
        title="No stock history yet"
        description="Stock value appears once inventory is received or sold."
      />
      <div v-else class="h-72">
        <LineChart :data="stockValueByMonth" x="label" :y="['value']" />
      </div>
    </section>

    <div class="mt-6 grid gap-6 lg:grid-cols-2">
      <section class="rounded-5 border border-outline-gray-1 p-4">
        <h2 class="text-lg-semibold text-ink-gray-8">Sell-through rate</h2>
        <p class="mt-1 text-sm text-ink-gray-5">Units sold in the last 30 days against what's on the shelf.</p>
        <Skeleton v-if="reportRequest.loading && !velocity.length" class="h-64 w-full rounded" />
        <EmptyState v-else-if="!hasValues(velocity, 'rate')" compact v-bind="noSellThroughState" />
        <div v-else class="h-64">
          <BarChart :data="velocity" x="product" :y="['rate']" />
        </div>
      </section>
      <section class="rounded-5 border border-outline-gray-1 p-4">
        <h2 class="text-lg-semibold text-ink-gray-8">Days of cover</h2>
        <p class="mt-1 text-sm text-ink-gray-5">How long today's stock lasts at the last 30 days' pace.</p>
        <Skeleton v-if="reportRequest.loading && !velocity.length" class="h-64 w-full rounded" />
        <EmptyState v-else-if="!hasValues(velocity, 'days')" compact v-bind="noCoverState" />
        <div v-else class="h-64">
          <BarChart :data="velocity" x="product" :y="['days']" />
        </div>
      </section>
    </div>

    <section class="mt-6 rounded-5 border border-outline-gray-1">
      <div class="flex items-center justify-between px-4 py-3">
        <div>
          <h2 class="text-lg-semibold text-ink-gray-8">Dead stock</h2>
          <p class="mt-1 text-sm text-ink-gray-5">Products with no sales in the last 30 days.</p>
        </div>
        <Button label="Open inventory" icon-right="lucide-arrow-right" route="/inventory" />
      </div>
      <div class="overflow-x-auto px-2 pb-2">
        <List
          class="min-w-[46rem]"
          :columns="['minmax(0,1fr)', '10rem', '6rem', '8rem', '8rem']"
          :row-height="Math.max(ia.density, 44)"
        >
          <ListHeader>
            <ListHeaderCell>Product</ListHeaderCell>
            <ListHeaderCell>Variant</ListHeaderCell>
            <ListHeaderCell>On hand</ListHeaderCell>
            <ListHeaderCell>Last sold</ListHeaderCell>
            <ListHeaderCell>Tied-up value</ListHeaderCell>
          </ListHeader>
          <ListSkeleton v-if="reportRequest.loading && !deadStock.length" :columns="5" />
          <ListRows v-else :items="deadStock" row-key="sku" v-slot="{ item }">
            <ListRow :value="item.sku">
              <ListCell><span class="truncate text-base text-ink-gray-8">{{ item.product }}</span></ListCell>
              <ListCell><span class="truncate text-base text-ink-gray-6">{{ item.variant }}</span></ListCell>
              <ListCell><span class="text-base text-ink-gray-6 tabular-nums">{{ item.stock }}</span></ListCell>
              <ListCell>
                <Badge
                  :label="item.last_sold_days != null ? `${item.last_sold_days} days ago` : 'Never sold'"
                  theme="orange"
                  variant="subtle"
                />
              </ListCell>
              <ListCell><span class="text-base text-ink-gray-7 tabular-nums">{{ money(item.value) }}</span></ListCell>
            </ListRow>
          </ListRows>
        </List>
        <!-- An empty dead-stock table is the good outcome, so this state congratulates rather
             than apologises — do not reword it into a generic "no data". -->
        <EmptyState
          v-if="!reportRequest.loading && !deadStock.length"
          compact
          icon="lucide-circle-check"
          title="Nothing is sitting still"
          description="Every product has sold in this period."
        />
      </div>
    </section>
  </PageBody>
</template>
