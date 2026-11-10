<script setup>
import { computed } from 'vue'
import Thumb from '../Thumb.vue'
import { money, priceRange, stockTone } from '../../data/format'

const props = defineProps({
  product: { type: Object, required: true },
  stats: { type: Object, required: true },
})

const priceLabel = computed(() => priceRange(props.stats.priceLow, props.stats.priceHigh))

const needsAttention = computed(() => props.stats.outOfStock + props.stats.lowStock)
</script>

<!-- The standing answer to "how is this product doing". Nothing here is an
     editor: everything editable lives in the form to the left, and repeating
     it here would only raise the question of which copy is real. -->
<template>
  <div class="divide-y divide-outline-gray-1">
    <section class="px-4 py-4">
      <h3 class="text-sm text-ink-gray-5">{{ __('At a glance') }}</h3>
      <dl class="mt-3 space-y-2">
        <div class="flex items-baseline justify-between gap-3">
          <dt class="text-base text-ink-gray-6">{{ __('Price') }}</dt>
          <dd class="text-base text-ink-gray-8 tabular-nums">{{ priceLabel }}</dd>
        </div>
        <div class="flex items-baseline justify-between gap-3">
          <dt class="text-base text-ink-gray-6">{{ __('On hand') }}</dt>
          <dd class="text-base text-ink-gray-7 tabular-nums">{{ stats.onHand }}</dd>
        </div>
        <div class="flex items-baseline justify-between gap-3">
          <dt class="text-base text-ink-gray-6">{{ __('Committed') }}</dt>
          <dd class="text-base text-ink-gray-7 tabular-nums">{{ stats.committed }}</dd>
        </div>
        <div class="flex items-baseline justify-between gap-3">
          <dt class="text-base text-ink-gray-6">{{ __('Available') }}</dt>
          <dd class="text-base tabular-nums" :class="stockTone(stats.available)">
            {{ stats.available }}
          </dd>
        </div>
      </dl>
    </section>

    <section class="px-4 py-4">
      <h3 class="text-sm text-ink-gray-5">{{ __('Last 30 days') }}</h3>
      <div class="mt-3 grid grid-cols-3 gap-3">
        <div>
          <p class="text-lg text-ink-gray-9 tabular-nums">{{ stats.unitsSold }}</p>
          <p class="mt-0.5 text-sm text-ink-gray-5">{{ __('sold') }}</p>
        </div>
        <div>
          <p class="text-lg text-ink-gray-9 tabular-nums">{{ stats.orderCount }}</p>
          <p class="mt-0.5 text-sm text-ink-gray-5">{{ __('orders') }}</p>
        </div>
        <div>
          <p class="text-lg text-ink-gray-9 tabular-nums">{{ money(stats.revenue) }}</p>
          <p class="mt-0.5 text-sm text-ink-gray-5">{{ __('revenue') }}</p>
        </div>
      </div>
    </section>

    <section v-if="needsAttention" class="px-4 py-4">
      <h3 class="text-sm text-ink-gray-5">{{ __('Needs attention') }}</h3>
      <p class="mt-2 text-p-sm text-ink-gray-7">
        <span v-if="stats.outOfStock" class="text-ink-red-6">{{ __('{0} out of stock', [stats.outOfStock]) }}</span>
        <span v-if="stats.outOfStock && stats.lowStock"> · </span>
        <span v-if="stats.lowStock" class="text-ink-amber-7">{{ __('{0} running low', [stats.lowStock]) }}</span>
      </p>
      <ul class="mt-3 space-y-2">
        <li v-for="row in stats.lowVariants" :key="row.id" class="flex items-center gap-2.5">
          <Thumb :image="row.image" size="size-6" />
          <span class="min-w-0 flex-1 truncate text-base text-ink-gray-7">{{ row.title }}</span>
          <span class="text-base tabular-nums" :class="stockTone(row.stock)">{{ row.stock }}</span>
        </li>
      </ul>
    </section>
  </div>
</template>
