<script setup>
import { computed, ref } from 'vue'
import { Badge, Skeleton } from 'frappe-ui'
import { AreaChart, DonutChart, FunnelChart } from 'frappe-ui/charts'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import ReportHeader from '../../components/ReportHeader.vue'
import ReportStats from '../../components/ReportStats.vue'
import PageBody from '../../components/PageBody.vue'
import EmptyState from '../../components/EmptyState.vue'
import ListSkeleton from '../../components/ListSkeleton.vue'
import { useAdminRead } from '../../data/api'
import { hasValues, monthsForRange } from '../../data/analytics'
import { ia } from '../../ia/store'

const range = ref('Last 12 months')
const compare = ref(true)

// Thin client over commera.api.admin.analytics.get_storefront_report, itself a wrapper around the
// Desk analytics dashboard's own (already SQL-aggregated) storefront queries — this report and
// that dashboard never disagree on what a session or a conversion means.
const reportRequest = useAdminRead('analytics.get_storefront_report', {
  params: () => ({ months: monthsForRange(range.value) }),
  refetch: true,
})

const report = computed(() => reportRequest.data)
const sessionsByMonth = computed(() => report.value?.sessions_by_month ?? [])
const channels = computed(() => report.value?.channels ?? [])
// The server's stage labels ("Viewed Product", "Reached Checkout") are written for the Desk
// dashboard's full-width funnel; in this half-width card five of them share the axis and the chart
// clips each to about seven characters, so four of the five read as "Viewed…". Shortened here
// rather than on the server, which the Desk screen shares.
const FUNNEL_STAGE_LABELS = {
  'Viewed Product': 'Viewed',
  'Added to Cart': 'Added',
  'Reached Checkout': 'Checkout',
  Purchased: 'Bought',
}

const funnel = computed(() =>
  (report.value?.funnel ?? []).map((row) => ({
    ...row,
    stage: FUNNEL_STAGE_LABELS[row.stage] ?? row.stage,
  })),
)
const topPages = computed(() => report.value?.top_pages ?? [])
const searchTerms = computed(() => report.value?.search_terms ?? [])

function delta(stat) {
  if (!stat || !stat.previous) return null
  return Math.round((stat.value - stat.previous) * 10) / 10
}

function ratePointsLabel(stat) {
  const change = delta(stat)
  return change == null ? null : `${change >= 0 ? '+' : ''}${change}pt`
}

function countDeltaLabel(stat) {
  if (!stat || !stat.previous) return null
  const change = Math.round(((stat.value - stat.previous) / stat.previous) * 1000) / 10
  return `${change >= 0 ? '+' : ''}${change}%`
}

const stats = computed(() => {
  const stat = report.value?.stats ?? {}
  return [
    {
      label: 'Sessions',
      value: (stat.sessions?.value ?? 0).toLocaleString('en-IN'),
      delta: countDeltaLabel(stat.sessions),
      up: (stat.sessions?.value ?? 0) >= (stat.sessions?.previous ?? 0),
    },
    {
      label: 'Conversion',
      value: `${stat.conversion_rate?.value ?? 0}%`,
      delta: ratePointsLabel(stat.conversion_rate),
      up: (stat.conversion_rate?.value ?? 0) >= (stat.conversion_rate?.previous ?? 0),
    },
    {
      label: 'Add to cart',
      value: `${stat.add_to_cart_rate?.value ?? 0}%`,
      delta: ratePointsLabel(stat.add_to_cart_rate),
      up: (stat.add_to_cart_rate?.value ?? 0) >= (stat.add_to_cart_rate?.previous ?? 0),
    },
    {
      label: 'Checkout completion',
      value: `${stat.checkout_completion_rate?.value ?? 0}%`,
      delta: ratePointsLabel(stat.checkout_completion_rate),
      up: (stat.checkout_completion_rate?.value ?? 0) >= (stat.checkout_completion_rate?.previous ?? 0),
    },
  ]
})
</script>

<template>
  <ReportHeader title="Storefront" v-model:range="range" v-model:compare="compare" />

  <PageBody width="narrow">
    <div>
      <h1 class="text-2xl text-ink-gray-9">Storefront</h1>
      <p class="mt-1 text-p-base text-ink-gray-6">
        Who reaches the store, what they look at, where they drop out. {{ range }}.
      </p>
    </div>

    <ReportStats
      class="mt-5"
      :stats="stats"
      :compare="compare"
      :loading="reportRequest.loading && !report"
    />

    <section class="mt-6 rounded-5 border border-outline-gray-1 p-4">
      <h2 class="text-lg-semibold text-ink-gray-8">Sessions over time</h2>
      <Skeleton v-if="reportRequest.loading && !sessionsByMonth.length" class="h-72 w-full rounded" />
      <EmptyState
        v-else-if="!hasValues(sessionsByMonth, 'sessions')"
        compact
        icon="lucide-chart-line"
        title="No sessions in this period"
        description="Try a wider date range."
      />
      <div v-else class="h-72">
        <AreaChart :data="sessionsByMonth" x="label" :y="['sessions']" />
      </div>
    </section>

    <!-- Three fifths to the funnel, two to the donut: the funnel splits its width across five
         stage columns and truncates each label at what is left, while the donut reads the same at
         any width. An even split leaves 56px a stage, which is a character short of "Checkout". -->
    <div class="mt-6 grid gap-6 lg:grid-cols-5">
      <section class="rounded-5 border border-outline-gray-1 p-4 lg:col-span-2">
        <h2 class="text-lg-semibold text-ink-gray-8">Where they come from</h2>
        <Skeleton v-if="reportRequest.loading && !channels.length" class="h-64 w-full rounded" />
        <EmptyState
          v-else-if="!hasValues(channels, 'sessions')"
          compact
          icon="lucide-chart-pie"
          title="No traffic sources yet"
          description="Channels appear once shoppers reach the storefront."
        />
        <div v-else class="h-64">
          <DonutChart :data="channels" category="channel" value="sessions" />
        </div>
      </section>
      <section class="rounded-5 border border-outline-gray-1 p-4 lg:col-span-3">
        <h2 class="text-lg-semibold text-ink-gray-8">Checkout funnel</h2>
        <Skeleton v-if="reportRequest.loading && !funnel.length" class="h-64 w-full rounded" />
        <EmptyState
          v-else-if="!hasValues(funnel, 'count')"
          compact
          icon="lucide-filter"
          title="No checkout activity yet"
          description="The funnel fills in once shoppers start browsing."
        />
        <div v-else class="h-64">
          <FunnelChart :data="funnel" category="stage" value="count" />
        </div>
      </section>
    </div>

    <section class="mt-6 rounded-5 border border-outline-gray-1">
      <h2 class="px-4 py-3 text-lg-semibold text-ink-gray-8">Top pages</h2>
      <p class="px-4 text-sm text-ink-gray-5">
        Landing sessions per page — the storefront doesn't record a separate page-view count.
      </p>
      <div class="px-2 pb-2">
        <List :columns="['minmax(0,1fr)', '8rem', '8rem']" :row-height="Math.max(ia.density, 44)">
          <ListHeader>
            <ListHeaderCell>Page</ListHeaderCell>
            <ListHeaderCell>Views</ListHeaderCell>
            <ListHeaderCell>Conversion</ListHeaderCell>
          </ListHeader>
          <ListSkeleton v-if="reportRequest.loading && !topPages.length" :columns="3" />
          <ListRows v-else :items="topPages" row-key="page" v-slot="{ item }">
            <ListRow :value="item.page">
              <ListCell><span class="truncate text-base text-ink-gray-8">{{ item.page }}</span></ListCell>
              <ListCell><span class="text-base text-ink-gray-6 tabular-nums">{{ item.views.toLocaleString('en-IN') }}</span></ListCell>
              <ListCell><span class="text-base text-ink-gray-6 tabular-nums">{{ item.conversion }}%</span></ListCell>
            </ListRow>
          </ListRows>
        </List>
        <EmptyState
          v-if="!reportRequest.loading && !topPages.length"
          compact
          icon="lucide-file-text"
          title="No page views yet"
          description="Views appear once shoppers browse the storefront."
        />
      </div>
    </section>

    <section class="mt-6 rounded-5 border border-outline-gray-1">
      <h2 class="px-4 py-3 text-lg-semibold text-ink-gray-8">Search terms</h2>
      <div v-if="searchTerms.length" class="px-2 pb-2">
        <List :columns="['minmax(0,1fr)', '8rem', '8rem']" :row-height="Math.max(ia.density, 44)">
          <ListHeader>
            <ListHeaderCell>Term</ListHeaderCell>
            <ListHeaderCell>Searches</ListHeaderCell>
            <ListHeaderCell>Results</ListHeaderCell>
          </ListHeader>
          <ListRows :items="searchTerms" row-key="term" v-slot="{ item }">
            <ListRow :value="item.term">
              <ListCell><span class="truncate text-base text-ink-gray-8">{{ item.term }}</span></ListCell>
              <ListCell><span class="text-base text-ink-gray-6 tabular-nums">{{ item.searches }}</span></ListCell>
              <ListCell>
                <Badge v-if="!item.results" label="No results" theme="red" variant="subtle" />
                <span v-else class="text-base text-ink-gray-6 tabular-nums">{{ item.results }}</span>
              </ListCell>
            </ListRow>
          </ListRows>
        </List>
      </div>
      <!-- commera's storefront tracking (Storefront Analytics Event) doesn't capture site search
           at all — no search-term field exists on the doctype. Kept as an honest empty state
           rather than a fabricated table; see docs/commera-open-questions.md. -->
      <EmptyState
        v-else
        compact
        icon="lucide-search"
        title="Not tracked yet"
        description="The storefront doesn't record search terms."
      />
    </section>
  </PageBody>
</template>
