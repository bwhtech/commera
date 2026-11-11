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
import { compactMoney, count, money } from '../../data/format'
import { __ } from '../../data/translation'
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
    { label: __('Stock value'), value: compactMoney(stat.stock_value?.value ?? 0), delta: null, up: true },
    { label: __('Units on hand'), value: count(stat.units_on_hand?.value), delta: null, up: true },
    {
      label: __('Days of cover'),
      value: stat.days_of_cover?.value != null ? String(stat.days_of_cover.value) : '—',
      delta: null,
      up: true,
    },
    { label: __('Capital in dead stock'), value: compactMoney(stat.dead_stock_value?.value ?? 0), delta: null, up: false },
  ]
})

// Both velocity panels read the same series, but they measure different things — a sell-through of
// zero is "nothing has sold", a cover of zero is "there is no pace to project from" — so each says
// why its own bars are missing.
const noSellThroughState = {
  icon: 'lucide-chart-column',
  title: __('No movement yet'),
  description: __('Stock movement appears once products start selling.'),
}
const noCoverState = {
  icon: 'lucide-timer',
  title: __('No sales pace yet'),
  description: __('Days of cover needs recent sales to project from.'),
}
</script>

<template>
  <ReportHeader :title="__('Inventory')" v-model:range="range" v-model:compare="compare" />

  <PageBody width="narrow">
    <div>
      <h1 class="text-2xl text-ink-gray-9">{{ __('Inventory') }}</h1>
      <p class="mt-1 text-p-base text-ink-gray-6">
        {{ __('How much capital the shelves are holding, and how fast it turns. {0}.', [__(range)]) }}
      </p>
    </div>

    <ReportStats
      class="mt-5"
      :stats="stats"
      :compare="compare"
      :loading="reportRequest.loading && !report"
    />

    <!-- Heights are the finished card's — padding, title, subtitle and plot — so the page does not
         jump when the real card replaces the block. Recheck them if either changes. -->
    <Skeleton
      v-if="reportRequest.loading && !stockValueByMonth.length"
      class="mt-6 h-[21.75rem] w-full rounded-5"
    />

    <section v-else class="mt-6 rounded-5 border border-outline-gray-1 p-4">
      <h2 class="text-lg-semibold text-ink-gray-8">{{ __('Stock value over time') }}</h2>
      <EmptyState
        v-if="!hasValues(stockValueByMonth, 'value')"
        compact
        icon="lucide-chart-line"
        :title="__('No stock history yet')"
        :description="__('Stock value appears once inventory is received or sold.')"
      />
      <div v-else class="h-72">
        <LineChart :data="stockValueByMonth" x="label" :y="['value']" palette="categorical" />
      </div>
    </section>

    <div class="mt-6 grid gap-6 lg:grid-cols-2">
      <Skeleton v-if="reportRequest.loading && !velocity.length" class="h-[21.25rem] w-full rounded-5" />

      <section v-else class="rounded-5 border border-outline-gray-1 p-4">
        <h2 class="text-lg-semibold text-ink-gray-8">{{ __('Sell-through rate') }}</h2>
        <p class="mt-1 text-sm text-ink-gray-5">{{ __("Units sold in the last 30 days against what's on the shelf.") }}</p>
        <EmptyState v-if="!hasValues(velocity, 'rate')" compact v-bind="noSellThroughState" />
        <div v-else class="h-64">
          <BarChart :data="velocity" x="product" :y="['rate']" />
        </div>
      </section>
      <Skeleton v-if="reportRequest.loading && !velocity.length" class="h-[21.25rem] w-full rounded-5" />

      <section v-else class="rounded-5 border border-outline-gray-1 p-4">
        <h2 class="text-lg-semibold text-ink-gray-8">{{ __('Days of cover') }}</h2>
        <p class="mt-1 text-sm text-ink-gray-5">{{ __("How long today's stock lasts at the last 30 days' pace.") }}</p>
        <EmptyState v-if="!hasValues(velocity, 'days')" compact v-bind="noCoverState" />
        <div v-else class="h-64">
          <BarChart :data="velocity" x="product" :y="['days']" />
        </div>
      </section>
    </div>

    <section class="mt-6 rounded-5 border border-outline-gray-1">
      <div class="flex items-center justify-between px-4 py-3">
        <div>
          <h2 class="text-lg-semibold text-ink-gray-8">{{ __('Dead stock') }}</h2>
          <p class="mt-1 text-sm text-ink-gray-5">{{ __('Products with no sales in the last 30 days.') }}</p>
        </div>
        <Button :label="__('Open inventory')" icon-right="lucide-arrow-right rtl:-scale-x-100" route="/inventory" />
      </div>
      <div class="overflow-x-auto px-2 pb-2">
        <List
          class="min-w-[46rem]"
          :columns="['minmax(0,1fr)', '10rem', '6rem', '8rem', '8rem']"
          :row-height="Math.max(ia.density, 44)"
        >
          <ListHeader>
            <ListHeaderCell>{{ __('Product') }}</ListHeaderCell>
            <ListHeaderCell>{{ __('Variant') }}</ListHeaderCell>
            <ListHeaderCell>{{ __('On hand') }}</ListHeaderCell>
            <ListHeaderCell>{{ __('Last sold') }}</ListHeaderCell>
            <ListHeaderCell>{{ __('Tied-up value') }}</ListHeaderCell>
          </ListHeader>
          <ListSkeleton v-if="reportRequest.loading && !deadStock.length" :columns="5" />
          <ListRows v-else :items="deadStock" row-key="sku" v-slot="{ item }">
            <ListRow :value="item.sku">
              <ListCell><span class="truncate text-base text-ink-gray-8">{{ item.product }}</span></ListCell>
              <ListCell><span class="truncate text-base text-ink-gray-6">{{ item.variant }}</span></ListCell>
              <ListCell><span class="text-base text-ink-gray-6 tabular-nums">{{ item.stock }}</span></ListCell>
              <ListCell>
                <Badge
                  :label="item.last_sold_days != null ? __('{0} days ago', [item.last_sold_days]) : __('Never sold')"
                  theme="amber"
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
          :title="__('Nothing is sitting still')"
          :description="__('Every product has sold in this period.')"
        />
      </div>
    </section>
  </PageBody>
</template>
