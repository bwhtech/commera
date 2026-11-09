<script setup>
import { computed } from 'vue'
import { Badge, Progress } from 'frappe-ui'
import { STATUS_THEMES } from '../../data/shopifyImport'

const props = defineProps({ run: { type: Object, required: true } })

const rows = computed(() =>
  props.run.progress.map((row) => {
    const done = row.created + row.updated + row.skipped + row.failed
    return { ...row, done, percent: row.total ? Math.round((done / row.total) * 100) : 0 }
  }),
)
</script>

<template>
  <div class="space-y-5">
    <p v-if="run.error_message" class="text-p-sm text-ink-red-6">{{ run.error_message }}</p>

    <div v-if="rows.length" class="divide-y divide-outline-gray-1 border-y border-outline-gray-1">
      <div v-for="row in rows" :key="row.resource" class="py-3">
        <div class="flex items-center gap-3">
          <span class="min-w-0 flex-1 truncate text-base-semibold text-ink-gray-8">{{ row.resource }}</span>
          <span class="shrink-0 text-sm text-ink-gray-5 tabular-nums">{{ row.done }} / {{ row.total }}</span>
          <Badge class="shrink-0" :label="row.status" :theme="STATUS_THEMES[row.status]" variant="subtle" />
        </div>
        <Progress class="mt-2" size="sm" :value="row.percent" />
        <div class="mt-1 text-sm text-ink-gray-5 tabular-nums">
          {{ row.created }} created · {{ row.updated }} updated · {{ row.skipped }} unchanged ·
          <span :class="row.failed ? 'text-ink-red-6' : ''">{{ row.failed }} failed</span>
        </div>
      </div>
    </div>

    <div v-if="run.issues.length">
      <div class="text-base-semibold text-ink-gray-8">
        Issues <span class="text-ink-gray-5 tabular-nums">· {{ run.issue_count }}</span>
      </div>
      <div class="mt-2 divide-y divide-outline-gray-1 border-y border-outline-gray-1">
        <div v-for="(issue, index) in run.issues" :key="index" class="flex items-start gap-3 py-2">
          <Badge
            class="mt-0.5 shrink-0"
            :label="issue.level"
            :theme="issue.level === 'Error' ? 'red' : 'orange'"
            variant="subtle"
          />
          <div class="min-w-0 flex-1">
            <div class="truncate text-sm text-ink-gray-8">{{ issue.resource }}<template v-if="issue.title"> · {{ issue.title }}</template></div>
            <p class="text-p-sm text-ink-gray-6">{{ issue.message }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
