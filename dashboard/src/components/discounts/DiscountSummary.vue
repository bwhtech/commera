<script setup>
import { computed } from 'vue'
import { NumberCard } from 'frappe-ui/charts'
import StatusBadge from '../StatusBadge.vue'
import { money, moneyIn } from '../../data/format'
import { discountHeading, discountTypeLabel, statusKey, summaryLines } from '../../data/discounts'

const props = defineProps({ discount: { type: Object, required: true } })

const status = computed(() => props.discount.status ?? (props.discount.enabled ? 'Active' : 'Disabled'))
const performance = computed(() => props.discount.performance)
</script>

<template>
  <section class="rounded-5 border border-outline-gray-1 p-4">
    <div class="flex items-center justify-between gap-2">
      <h2 class="truncate text-base-semibold text-ink-gray-8">{{ discountHeading(discount) }}</h2>
      <StatusBadge :status="statusKey(status)" />
    </div>
    <p class="mt-0.5 text-sm text-ink-gray-5">
      {{ discount.method === 'Code' ? 'Code' : 'Automatic' }} · {{ discountTypeLabel(discount) }}
    </p>
    <ul class="mt-3 list-disc space-y-1 pl-4 text-p-sm text-ink-gray-7">
      <li v-for="line in summaryLines(discount)" :key="line">{{ line }}</li>
    </ul>
  </section>

  <div v-if="performance" class="grid grid-cols-2 gap-3">
    <NumberCard title="Orders" :value="performance.orders" />
    <NumberCard title="Discount given" :value="money(performance.discount_given)" />
    <NumberCard title="Sales" :value="money(performance.sales)" />
    <NumberCard title="Budget left" :value="performance.budget_left == null ? '—' : moneyIn(performance.budget_left, discount.currency)" />
  </div>
</template>
