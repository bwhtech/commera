<script setup>
import { computed } from 'vue'
import { __ } from '../../data/translation'
import { SAMPLE_PRODUCTS } from '../../ia/onboarding'
import SwatchDot from '../SwatchDot.vue'
import ShippingArt from './ShippingArt.vue'

const props = defineProps({
  kind: { type: String, required: true },
  // `{ slug, category, country, codEnabled, primaryColor, look }`, from Home's read.
  store: { type: Object, required: true },
})

const PRODUCT_TILES = ['bg-surface-amber-2', 'bg-surface-blue-2', 'bg-surface-green-2']
// Listed per position: Tailwind only generates names it can read.
const FAN = [
  'origin-bottom -translate-x-[115%] -rotate-[9deg] shadow-sm group-hover:-translate-x-[130%] group-hover:-rotate-[13deg]',
  'z-10 -translate-y-1 shadow-lg group-hover:-translate-y-2.5',
  'origin-bottom translate-x-[15%] rotate-[9deg] shadow-sm group-hover:translate-x-[30%] group-hover:rotate-[13deg]',
]
const SWATCH_SPREAD = ['group-hover:-translate-y-1.5', 'z-10 -mt-3', '-mt-3 group-hover:translate-y-1.5']
const METHOD_DELAYS = ['delay-0', 'delay-75', 'delay-150']

const productIcons = computed(() => (SAMPLE_PRODUCTS[props.store.category] ?? SAMPLE_PRODUCTS.Other).slice(0, 3))
const methods = computed(() => [
  { label: 'UPI', on: false },
  { label: __('Card'), on: false },
  { label: 'COD', on: props.store.codEnabled },
])
const swatches = computed(() => [props.store.primaryColor, null, null])
</script>

<template>
  <div class="relative flex h-36 items-center justify-center overflow-hidden rounded-4 bg-surface-gray-1" aria-hidden="true">
    <span class="absolute bottom-6 h-3 w-40 rounded-full bg-surface-gray-4 opacity-60 blur-md" />

    <template v-if="kind === 'payments'">
      <div
        class="absolute h-[4.5rem] w-[7.25rem] -translate-x-6 -translate-y-2 -rotate-[8deg] rounded-5 bg-surface-gray-3 shadow-sm transition-transform duration-300 ease-out-strong motion-reduce:transition-none group-hover:-translate-x-8 group-hover:-rotate-[13deg]"
      />
      <div
        class="relative flex h-[4.5rem] w-[7.25rem] translate-x-2 flex-col justify-between rounded-5 bg-surface-base p-2.5 shadow-lg ring-1 ring-outline-gray-1 transition-transform duration-300 ease-out-strong motion-reduce:transition-none group-hover:-translate-y-1 group-hover:rotate-2"
      >
        <div class="flex items-center justify-between">
          <span class="h-3.5 w-5 rounded-1 bg-surface-amber-3" />
          <span class="lucide-nfc size-3.5 text-ink-gray-4" />
        </div>
        <p class="text-2xs text-ink-gray-5 tabular-nums">•••• 4242</p>
      </div>
      <div class="absolute bottom-3 end-4 flex gap-1">
        <span
          v-for="(method, index) in methods"
          :key="method.label"
          class="flex items-center gap-1 rounded-full bg-surface-base px-2 py-0.5 text-2xs text-ink-gray-7 shadow-sm ring-1 ring-outline-gray-1 transition-transform duration-300 ease-out-strong motion-reduce:transition-none group-hover:-translate-y-0.5"
          :class="METHOD_DELAYS[index]"
        >
          <span v-if="method.on" class="lucide-check size-3 text-ink-green-5" />
          {{ method.label }}
        </span>
      </div>
    </template>

    <ShippingArt v-else-if="kind === 'shipping'" :country="store.country" />

    <div v-else-if="kind === 'products'" class="flex items-end">
      <div class="relative h-[5.75rem] w-44">
        <div
          v-for="(icon, index) in productIcons"
          :key="icon"
          class="absolute bottom-0 left-1/2 w-16 -translate-x-1/2 rounded-4 bg-surface-base p-1.5 ring-1 ring-outline-gray-1 transition-transform duration-300 ease-out-strong motion-reduce:transition-none"
          :class="FAN[index]"
        >
          <div class="flex aspect-square items-center justify-center rounded-1 text-ink-gray-5" :class="PRODUCT_TILES[index]">
            <span class="size-5" :class="icon" />
          </div>
          <div class="mt-1.5 h-1.5 w-9 rounded-full bg-surface-gray-3" />
          <div class="mt-1 h-1.5 w-5 rounded-full bg-surface-gray-2" />
        </div>
      </div>
      <div
        class="ms-5 flex h-[5.375rem] w-16 items-center justify-center rounded-4 border border-dashed border-outline-gray-3 text-ink-gray-5 transition-[border-color,color,transform] duration-300 ease-out-strong motion-reduce:transition-none group-hover:-translate-y-1 group-hover:border-outline-gray-5 group-hover:text-ink-gray-8"
      >
        <span class="lucide-plus size-5" />
      </div>
    </div>

    <div v-else-if="kind === 'brand'" class="flex items-center gap-5">
      <div
        class="w-36 overflow-hidden rounded-4 bg-surface-base shadow-lg ring-1 ring-outline-gray-1 transition-transform duration-300 ease-out-strong motion-reduce:transition-none group-hover:-translate-y-1"
      >
        <div class="flex gap-1 border-b border-outline-gray-1 px-2 py-1.5">
          <span v-for="dot in 3" :key="dot" class="size-1.5 rounded-full bg-surface-gray-3" />
        </div>
        <div class="p-2">
          <div class="flex h-12 items-end justify-between p-2" :class="[store.look.hero, store.look.radius]">
            <span class="text-lg leading-none text-ink-gray-9" :class="store.look.heading">Aa</span>
            <SwatchDot :color="store.primaryColor" size="xs" />
          </div>
        </div>
      </div>
      <div class="flex flex-col">
        <span
          v-for="(colour, index) in swatches"
          :key="index"
          class="rounded-full bg-surface-base p-0.5 shadow-md transition-transform duration-300 ease-out-strong motion-reduce:transition-none"
          :class="SWATCH_SPREAD[index]"
        >
          <SwatchDot v-if="colour" :color="colour" size="lg" />
          <span v-else class="block size-8 rounded-full" :class="index === 1 ? 'bg-surface-gray-7' : 'bg-surface-gray-3'" />
        </span>
      </div>
    </div>

    <template v-else-if="kind === 'domain'">
      <div
        class="relative flex w-56 items-center gap-2 rounded-full bg-surface-base px-3.5 py-2.5 shadow-lg ring-1 ring-outline-gray-1 transition-transform duration-300 ease-out-strong motion-reduce:transition-none group-hover:scale-[1.02]"
      >
        <span class="lucide-lock size-3.5 shrink-0 text-ink-green-5" />
        <span class="min-w-0 truncate text-base">
          <span class="text-ink-gray-5">www.</span><span class="font-medium text-ink-gray-9">{{ store.slug }}</span><span class="text-ink-gray-9">.com</span>
        </span>
      </div>
      <span
        class="lucide-mouse-pointer-2 absolute bottom-5 right-14 size-7 fill-current text-ink-gray-9 drop-shadow transition-transform duration-300 ease-out-strong motion-reduce:transition-none group-hover:-translate-x-6 group-hover:-translate-y-4"
      />
    </template>
  </div>
</template>
