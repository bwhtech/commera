<script setup>
/**
 * What a settings panel shows while its first read is in flight.
 *
 * Shaped like SettingsRow — the label and its description on the left, one control on the
 * right — so nothing moves when the real fields land. It replaces frappe-ui's LoadingText,
 * which is a single centred word: on a panel that is otherwise a stack of rows that reads as
 * a stalled screen, and it is the one surface in the app that never learnt to skeleton.
 *
 * `lines` is how many text bars the left column carries, because a panel's row is not always
 * a label and a description — a delivery option carries a third line for its price.
 */
import { Skeleton } from 'frappe-ui'

defineProps({
  rows: { type: Number, default: 4 },
  lines: { type: Number, default: 2 },
})

// A stack of identical bars reads as a progress bar rather than as content. Cycling the
// widths gives the block the ragged edge a real column of labels has.
const labelWidths = ['w-28', 'w-36', 'w-24', 'w-32']
const detailWidths = ['w-56', 'w-44', 'w-64', 'w-48']
</script>

<template>
  <div class="divide-y divide-outline-gray-1" aria-hidden="true">
    <div v-for="row in rows" :key="row" class="flex items-center gap-8 py-3.5">
      <div class="min-w-0 flex-1">
        <Skeleton class="h-4 rounded" :class="labelWidths[row % labelWidths.length]" />
        <!-- max-w-full: the settings dialog is narrow on a phone, and a fixed-width bar
             would push the control off the panel's own edge. -->
        <Skeleton
          v-for="line in lines - 1"
          :key="line"
          class="mt-2 h-3.5 max-w-full rounded"
          :class="detailWidths[(row + line) % detailWidths.length]"
        />
      </div>
      <Skeleton class="h-7 w-40 shrink-0 rounded" />
    </div>
  </div>
</template>
