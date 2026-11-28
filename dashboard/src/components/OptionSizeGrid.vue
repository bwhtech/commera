<script setup>
/**
 * The color x size matrix: every pair starts carried, and the owner unticks the ones
 * this product does not come in, so a color can carry a subset of the sizes.
 */
import { computed } from 'vue'
import { Checkbox } from 'frappe-ui'
import SwatchDot from './SwatchDot.vue'
import { buildOptionSizes, pairKey } from '../data/optionSizes'
import { __ } from '../data/translation'

const props = defineProps({
  options: { type: Array, required: true },
  sizes: { type: Array, required: true },
  optionLabel: { type: String, default: () => __('Color') },
  swatches: { type: Object, default: () => ({}) },
  live: { type: Array, default: null },
})

const excluded = defineModel({ type: Array, required: true })

const emptyOptions = computed(
  () =>
    new Set(
      buildOptionSizes(props.options, props.sizes, excluded.value)
        .filter((row) => !row.sizes.length)
        .map((row) => row.option),
    ),
)

function isSelected(option, size) {
  return !excluded.value.includes(pairKey(option, size))
}

const liveKeys = computed(() => (props.live ? new Set(props.live) : null))

function cellTone(option, size) {
  if (!liveKeys.value) return ''
  const isLive = liveKeys.value.has(pairKey(option, size))
  const selected = isSelected(option, size)
  if (isLive && !selected) return 'bg-surface-red-2'
  if (!isLive && selected) return 'bg-surface-green-2'
  return ''
}

// The legend explains only the tones on screen: at rest, or with only additions, a key for a
// colour nobody can see is noise.
const shownTones = computed(() => {
  const tones = new Set()
  for (const option of props.options) {
    for (const size of props.sizes) tones.add(cellTone(option, size))
  }
  return { added: tones.has('bg-surface-green-2'), leaving: tones.has('bg-surface-red-2') }
})

// The sticky column paints over the cells scrolling under it, so it has to be the exact surface
// it sits on, or dark mode shows a band (base is 23, a dialog 31). The grid only lives in
// FormDialogs: frappe-ui's Dialog panel is surface-elevation-1 from `sm`, and below `sm` the
// dialog is a BottomSheet, which is surface-base. Recheck if the grid moves out of a dialog.
const STICKY_SURFACE = 'bg-surface-elevation-1 max-sm:bg-surface-base'

function cellLabel(option, size) {
  const tone = cellTone(option, size)
  if (tone === 'bg-surface-red-2') return __('{0} in size {1}, will leave the store', [option, size])
  if (tone === 'bg-surface-green-2') return __('{0} in size {1}, will be added', [option, size])
  return __('{0} in size {1}', [option, size])
}

function toggle(option, size, selected) {
  const key = pairKey(option, size)
  excluded.value = selected ? excluded.value.filter((entry) => entry !== key) : [...excluded.value, key]
}
</script>

<template>
  <div>
    <p class="mb-2 text-p-sm text-ink-gray-6">
      {{ __('Untick any size you do not carry in a {0}.', [optionLabel.toLowerCase()]) }}
    </p>
    <div class="overflow-x-auto rounded-4 border border-outline-gray-1">
      <table class="w-full min-w-max border-collapse text-start">
        <thead>
          <tr>
            <th class="sticky start-0 z-10 px-3 py-2 text-start text-sm font-normal text-ink-gray-6" :class="STICKY_SURFACE">
              {{ optionLabel }}
            </th>
            <th
              v-for="size in props.sizes"
              :key="size"
              class="px-3 py-2 text-center text-sm font-normal text-ink-gray-6"
            >
              {{ size }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="option in props.options" :key="option" class="border-t border-outline-gray-1">
            <th
              class="sticky start-0 z-10 max-w-40 px-3 py-2 text-start text-base font-normal"
              :class="[STICKY_SURFACE, emptyOptions.has(option) ? 'text-ink-red-7' : 'text-ink-gray-8']"
            >
              <span class="flex items-center gap-2">
                <SwatchDot
                  v-if="props.swatches[option]?.color || props.swatches[option]?.image"
                  :color="props.swatches[option]?.color"
                  :image="props.swatches[option]?.image"
                  size="sm"
                />
                <span class="truncate">{{ option }}</span>
              </span>
            </th>
            <td
              v-for="size in props.sizes"
              :key="size"
              class="px-3 py-2 text-center transition-colors"
              :class="cellTone(option, size)"
            >
              <Checkbox
                :model-value="isSelected(option, size)"
                :aria-label="cellLabel(option, size)"
                @update:model-value="toggle(option, size, $event)"
              />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p
      v-if="shownTones.added || shownTones.leaving"
      class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-gray-6"
    >
      <span v-if="shownTones.added" class="flex items-center gap-1.5">
        <span class="size-3 rounded-1 bg-surface-green-2" aria-hidden="true" />
        {{ __('Will be added') }}
      </span>
      <span v-if="shownTones.leaving" class="flex items-center gap-1.5">
        <span class="size-3 rounded-1 bg-surface-red-2" aria-hidden="true" />
        {{ __('Will leave the store') }}
      </span>
    </p>
  </div>
</template>

