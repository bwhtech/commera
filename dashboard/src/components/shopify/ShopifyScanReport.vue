<script setup>
import { computed } from 'vue'
import { Badge } from 'frappe-ui'

const props = defineProps({ report: { type: Object, required: true } })

const LEVEL_THEMES = { warning: 'orange', info: 'gray' }

const counts = computed(() =>
  Object.entries(props.report.counts ?? {}).map(([resource, count]) => ({
    resource,
    // null means Shopify would not tell: a scope the app lacks, not an empty store.
    value: count === null ? '—' : count.toLocaleString(),
  })),
)
</script>

<template>
  <div class="space-y-5">
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
      <div v-for="row in counts" :key="row.resource" class="rounded-4 bg-surface-gray-1 px-3 py-2">
        <div class="text-sm text-ink-gray-5">{{ row.resource }}</div>
        <div class="text-lg-semibold text-ink-gray-9 tabular-nums">{{ row.value }}</div>
      </div>
    </div>

    <div v-if="report.findings?.length" class="divide-y divide-outline-gray-1 border-y border-outline-gray-1">
      <div v-for="finding in report.findings" :key="finding.title" class="flex items-start gap-3 py-3">
        <Badge
          class="mt-0.5 shrink-0"
          :label="finding.level === 'warning' ? 'Check' : 'Note'"
          :theme="LEVEL_THEMES[finding.level]"
          variant="subtle"
        />
        <div class="min-w-0 flex-1">
          <div class="text-base-semibold text-ink-gray-8">
            {{ finding.title }}
            <span v-if="finding.count" class="text-ink-gray-5 tabular-nums">· {{ finding.count }}</span>
          </div>
          <p class="text-p-sm text-ink-gray-6">{{ finding.detail }}</p>
          <p v-if="finding.examples?.length" class="mt-1 truncate text-p-sm text-ink-gray-5">
            {{ finding.examples.join(', ') }}
          </p>
        </div>
      </div>
    </div>
    <p v-else class="text-p-sm text-ink-gray-6">Everything in this store fits Commera.</p>
  </div>
</template>
