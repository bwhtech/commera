<script setup>
import { computed } from 'vue'
import Thumb from '../Thumb.vue'
import { money, priceRange, stockTone } from '../../data/format'
import { PLACEHOLDER_OPTION, PLACEHOLDER_SIZE } from '../../data/product'
import { __ } from '../../data/translation'

const props = defineProps({
  product: { type: Object, required: true },
  stats: { type: Object, required: true },
  // Stock warnings are for what shoppers can reach; a draft that never went live has nothing to warn about.
  isLive: { type: Boolean, required: true },
})

const ATTENTION_LIMIT = 4

const priceLabel = computed(() => priceRange(props.stats.priceLow, props.stats.priceHigh))
const hasSales = computed(() => props.stats.unitsSold > 0 || props.stats.orderCount > 0)

// "Black · M", leaving out the placeholder halves a product without colors or sizes carries.
function sizeLabel(variant, size) {
  const parts = [variant.option, size.size].filter((part) => part !== PLACEHOLDER_OPTION && part !== PLACEHOLDER_SIZE)
  return parts.join(' · ') || props.product.title
}

const lowSizes = computed(() =>
  props.product.variants
    .flatMap((variant) => variant.sizes.map((size) => ({ variant, size })))
    .filter(({ size }) => (size.stock ?? 0) <= 5)
    .sort((a, b) => (a.size.stock ?? 0) - (b.size.stock ?? 0))
    .map(({ variant, size }) => ({
      id: size.item_code,
      title: sizeLabel(variant, size),
      image: variant.images?.[0],
      stock: size.stock ?? 0,
    })),
)
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
          <dt class="text-base text-ink-gray-6">{{ __('In stock') }}</dt>
          <dd class="text-base text-ink-gray-7 tabular-nums">{{ stats.onHand }}</dd>
        </div>
        <div v-if="stats.committed" class="flex items-baseline justify-between gap-3">
          <dt class="text-base text-ink-gray-6">{{ __('Ordered, not shipped') }}</dt>
          <dd class="text-base text-ink-gray-7 tabular-nums">{{ stats.committed }}</dd>
        </div>
      </dl>
    </section>

    <section class="px-4 py-4">
      <h3 class="text-sm text-ink-gray-5">{{ __('Last 30 days') }}</h3>
      <div v-if="hasSales" class="mt-3 grid grid-cols-3 gap-3">
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
      <p v-else class="mt-2 text-p-sm text-ink-gray-5">{{ __('No sales yet.') }}</p>
    </section>

    <section v-if="isLive && lowSizes.length" class="px-4 py-4">
      <h3 class="text-sm text-ink-gray-5">{{ __('Needs stock') }}</h3>
      <ul class="mt-3 space-y-2">
        <li v-for="row in lowSizes.slice(0, ATTENTION_LIMIT)" :key="row.id" class="flex items-center gap-2.5">
          <Thumb :image="row.image" size="size-6" />
          <span class="min-w-0 flex-1 truncate text-base text-ink-gray-7">{{ row.title }}</span>
          <span class="text-base tabular-nums" :class="stockTone(row.stock)">{{ row.stock }}</span>
        </li>
      </ul>
      <p v-if="lowSizes.length > ATTENTION_LIMIT" class="mt-2 text-sm text-ink-gray-5">
        {{ __('{0} more', [lowSizes.length - ATTENTION_LIMIT]) }}
      </p>
    </section>
  </div>
</template>
