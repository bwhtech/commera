import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import * as Vue from 'vue'
import { compile } from '@vue/compiler-dom'
import { parse } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { hasValues } from '../../src/data/analytics.js'

async function renderRevenue(months) {
  const source = readFileSync(new URL('../../src/pages/analytics/Revenue.vue', import.meta.url), 'utf8')
  const { descriptor } = parse(source)
  const { code } = compile(descriptor.template.content, { mode: 'function', prefixIdentifiers: true })
  const render = new Function('Vue', code)(Vue)
  const state = {
    ia: { density: 44 },
    range: 'Last 12 months',
    compare: true,
    stats: [],
    months,
    rows: [],
    discounts: { given: 0, orders: 0, top: [] },
    reportRequest: { loading: false, error: null, data: { months } },
    hasValues,
    hasMonthlyActivity: true,
    money: String,
    compactMoney: String,
    noRevenueState: { icon: 'lucide-chart-line', title: 'No revenue in this period', description: 'Try a wider date range.' },
  }
  const app = Vue.createSSRApp({ render, setup: () => state })
  app.config.globalProperties.__ = (text, values = []) => text.replace(/\{(\d+)\}/g, (_match, index) => values[index])
  app.component('ListRows', {
    props: ['items'],
    render() { return Vue.h('div', this.items.map((item) => this.$slots.default({ item }))) },
  })
  app.component('EmptyState', {
    props: ['title', 'description'],
    render() { return Vue.h('p', { 'data-empty': '' }, `${this.title}|${this.description ?? ''}`) },
  })
  for (const name of ['ReportHeader', 'ReportStats', 'PageBody', 'List', 'ListHeader', 'ListRow', 'ListCell', 'ListSkeleton']) {
    app.component(name, { render() { return Vue.h('div', this.$slots.default?.()) } })
  }
  for (const name of ['ListHeaderCell', 'AreaChart', 'BarChart', 'Skeleton']) app.component(name, { render: () => null })
  return renderToString(app)
}

test('a period with revenue but no discounts does not claim there was no revenue', async () => {
  const html = await renderRevenue([{ label: 'Nov', revenue: 3199, orders: 1, aov: 3199, discounts: 0, refunds: 0 }])
  const emptyStates = [...html.matchAll(/data-empty[^>]*>([^<]*)</g)].map((match) => match[1])

  assert.ok(emptyStates.some((text) => text.startsWith('No discounts in this period')))
  assert.ok(!emptyStates.some((text) => text.startsWith('No revenue in this period')))
})
