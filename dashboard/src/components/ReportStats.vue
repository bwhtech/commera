<script setup>
import { Skeleton } from 'frappe-ui'

defineProps({
  stats: { type: Array, required: true },
  compare: { type: Boolean, default: false },
  // First load only — the callers pass `loading && !data`, because a refetch (a new date range)
  // keeps the previous answer on screen and would otherwise blank a populated strip.
  loading: { type: Boolean, default: false },
  // The analytics reports name their four tiles in the client, so the labels can stay put while
  // only the numbers are placeholders and nothing shifts when the data lands. The Overview strip
  // takes its labels from the server, so there is nothing to hold — those skeleton too.
  skeletonLabels: { type: Boolean, default: false },
})
</script>

<template>
  <div class="grid grid-cols-2 rounded-5 border border-outline-gray-1 sm:grid-cols-4 sm:divide-x sm:divide-outline-gray-2">
    <div v-for="stat in stats" :key="stat.key ?? stat.label" class="px-4 py-3.5">
      <Skeleton v-if="loading && skeletonLabels" class="h-3.5 w-20 rounded" />
      <p v-else class="text-sm text-ink-gray-5">{{ stat.label }}</p>

      <Skeleton v-if="loading" class="mt-1 h-7 w-24 rounded" />
      <p v-else class="mt-1 text-2xl text-ink-gray-9 tabular-nums">{{ stat.value }}</p>

      <Skeleton v-if="loading && skeletonLabels" class="mt-2 h-3.5 w-28 rounded" />
      <p
        v-else-if="compare && stat.delta"
        class="mt-1 text-sm"
        :class="stat.up ? 'text-ink-green-6' : 'text-ink-red-6'"
      >
        {{ stat.delta }} vs. previous period
      </p>
      <p v-else-if="stat.note" class="mt-1 truncate text-sm text-ink-gray-5">{{ stat.note }}</p>
      <p v-else class="mt-1 text-sm text-ink-gray-4">&nbsp;</p>
    </div>
  </div>
</template>
