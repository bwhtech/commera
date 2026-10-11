<script setup>
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import { NumberCard } from 'frappe-ui/charts'
import { money } from '../../data/format'
import { STATUS_THEMES, discountTypeByValue, summaryLines } from '../../data/discounts'

const props = defineProps({ discount: { type: Object, required: true } })

const heading = computed(() =>
  props.discount.method === 'Code' ? props.discount.code || 'No code yet' : props.discount.title || 'Untitled discount',
)
const status = computed(() => props.discount.status ?? (props.discount.enabled ? 'Active' : 'Disabled'))
const performance = computed(() => props.discount.performance)
</script>

<template>
  <section class="rounded-5 border border-outline-gray-1 p-4">
    <div class="flex items-center justify-between gap-2">
      <h2 class="truncate text-base-semibold text-ink-gray-8">{{ heading }}</h2>
      <Badge :label="status" :theme="STATUS_THEMES[status]" variant="subtle" />
    </div>
    <p class="mt-0.5 text-sm text-ink-gray-5">
      {{ discount.method === 'Code' ? 'Code' : 'Automatic' }} · {{ discountTypeByValue[discount.discount_type].label }}
    </p>
    <ul class="mt-3 list-disc space-y-1 pl-4 text-p-sm text-ink-gray-7">
      <li v-for="line in summaryLines(discount)" :key="line">{{ line }}</li>
    </ul>
  </section>

  <!-- A saved discount's results; a new one has none to show yet. -->
  <div v-if="performance" class="grid grid-cols-2 gap-3">
    <NumberCard title="Orders" :value="performance.orders" />
    <NumberCard title="Discount given" :value="money(performance.discount_given)" />
    <NumberCard title="Sales" :value="money(performance.sales)" />
    <NumberCard title="Budget left" :value="performance.budget_left == null ? '—' : money(performance.budget_left)" />
  </div>
</template>
