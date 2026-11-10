<script setup>
import { computed } from 'vue'
import { __ } from '../../data/translation'

const props = defineProps({ country: { type: String, default: '' } })

// The truck's `[offset-path:…]` class repeats this with `_` for spaces (Tailwind cannot read a
// variable): change both. The stage never scales, so offset-path and the SVG share one coordinate space.
const ROUTE = 'M 44 78 C 90 78, 104 54, 140 62 C 176 70, 194 62, 236 62'

const CITIES = {
  India: 'Mumbai',
  'United Arab Emirates': 'Dubai',
  'Saudi Arabia': 'Riyadh',
  'United Kingdom': 'London',
  'United States': 'Brooklyn',
  Germany: 'Berlin',
}
const city = computed(() => CITIES[props.country] ?? __('Your customer'))
</script>

<template>
  <!-- The truck's offset-distance (38%, 74% on hover) and the line's dash offset (62, 26) sum to
       100, so line and truck always meet. -->
  <div class="relative h-36 w-[17.5rem] shrink-0">
    <svg class="absolute inset-0" width="280" height="144" viewBox="0 0 280 144" fill="none" aria-hidden="true">
      <g class="text-ink-gray-2" stroke="currentColor" stroke-width="8" stroke-linecap="round" opacity="0.6">
        <path d="M -10 78 H 96" />
        <path d="M 184 62 H 290" />
        <path d="M 140 -10 V 160" />
      </g>
      <path :d="ROUTE" class="text-ink-gray-4" stroke="currentColor" stroke-width="2" stroke-dasharray="2 5" stroke-linecap="round" />
      <path
        :d="ROUTE"
        pathLength="100"
        stroke-dasharray="100 100"
        class="text-ink-gray-8 transition-[stroke-dashoffset] duration-[600ms] ease-in-out-strong [stroke-dashoffset:62] motion-reduce:transition-none group-hover:[stroke-dashoffset:26]"
        stroke="currentColor"
        stroke-width="2.5"
        stroke-linecap="round"
      />
    </svg>

    <span class="absolute left-6 top-[3.625rem] flex size-10 items-center justify-center rounded-full bg-surface-base shadow-md ring-1 ring-outline-gray-1">
      <span class="lucide-store size-[1.125rem] text-ink-gray-7" aria-hidden="true" />
    </span>

    <span class="absolute left-[13.5rem] top-[2.625rem] flex size-10 items-center justify-center rounded-full bg-surface-base shadow-md ring-1 ring-outline-gray-1">
      <span class="lucide-house size-[1.125rem] text-ink-gray-7" aria-hidden="true" />
    </span>

    <span
      class="absolute left-0 top-0 flex size-9 items-center justify-center rounded-full bg-surface-gray-9 shadow-lg transition-[offset-distance] duration-[600ms] ease-in-out-strong [offset-anchor:center] [offset-distance:38%] [offset-path:path('M_44_78_C_90_78,_104_54,_140_62_C_176_70,_194_62,_236_62')] [offset-rotate:0deg] motion-reduce:transition-none group-hover:[offset-distance:74%]"
    >
      <span class="lucide-truck size-4 text-ink-base" aria-hidden="true" />
    </span>

    <span class="absolute left-1/2 top-[6.5rem] flex -translate-x-1/2 items-center gap-1 whitespace-nowrap rounded-full bg-surface-base px-2 py-0.5 text-2xs text-ink-gray-7 shadow-sm ring-1 ring-outline-gray-1">
      <span class="lucide-clock size-3 text-ink-gray-5" aria-hidden="true" />
      {{ __('{0} · Thursday', [city]) }}
    </span>
  </div>
</template>
