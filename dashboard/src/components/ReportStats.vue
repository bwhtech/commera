<script setup>
import { Skeleton } from 'frappe-ui'

defineProps({
  stats: { type: Array, required: true },
  compare: { type: Boolean, default: false },
  // First load only — the callers pass `loading && !data`, because a refetch (a new date range)
  // keeps the previous answer on screen and would otherwise blank a populated strip.
  loading: { type: Boolean, default: false },
})
</script>

<template>
  <div class="grid grid-cols-2 rounded-5 border border-outline-gray-1 sm:grid-cols-4 sm:divide-x sm:divide-outline-gray-2 sm:rtl:divide-x-reverse">
    <div v-for="stat in stats" :key="stat.key ?? stat.label" class="px-4 py-3.5">
      <!-- h-20 is what the label, the reading and the line under it occupy together, so the strip
           keeps its height and nothing below it moves when the numbers land. -->
      <Skeleton v-if="loading" class="h-20 w-full rounded-4" />

      <template v-else>
        <p class="text-sm text-ink-gray-5">{{ stat.label }}</p>
        <p class="mt-1 text-2xl text-ink-gray-9 tabular-nums">{{ stat.value }}</p>

        <p
          v-if="compare && stat.delta"
          class="mt-1 text-sm"
          :class="stat.up ? 'text-ink-green-6' : 'text-ink-red-6'"
        >
          {{ __('{0} vs. previous period', [stat.delta]) }}
        </p>
        <p v-else-if="stat.note" class="mt-1 truncate text-sm text-ink-gray-5">{{ stat.note }}</p>
        <p v-else class="mt-1 text-sm text-ink-gray-4">&nbsp;</p>
      </template>
    </div>
  </div>
</template>
