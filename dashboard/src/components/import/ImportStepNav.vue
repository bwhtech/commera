<script setup>
import { computed } from 'vue'
import { Tooltip } from 'frappe-ui'
import { STEPS, canChangeStep, imp } from '../../data/importFlow'

const pct = computed(() => Math.round(((imp.step + 1) / STEPS.length) * 100))

// Only steps you have already reached are clickable, and none while a step is waiting on the
// server or after the import landed (see importPhase.js).
const go = (i) => {
  if (canChangeStep.value && i <= imp.step) imp.step = i
}
const state = (i) => (i < imp.step ? 'done' : i === imp.step ? 'current' : 'todo')
</script>

<template>
  <div class="space-y-2">
    <!-- Not items-baseline: the label and hint truncate, and a scroll container
         synthesizes its baseline from the border box instead of its text. -->
    <div class="flex items-center gap-2">
      <span class="min-w-0 truncate text-base-semibold text-ink-gray-8">{{ STEPS[imp.step].label }}</span>
      <span class="hidden min-w-0 truncate text-sm text-ink-gray-5 sm:inline">{{ STEPS[imp.step].hint }}</span>
      <span class="ms-auto shrink-0 text-sm text-ink-gray-5 tabular-nums">
        {{ __('Step {0} of {1}', [imp.step + 1, STEPS.length]) }}
      </span>
    </div>
    <div class="flex gap-1" role="progressbar" :aria-valuenow="pct">
      <Tooltip v-for="(s, i) in STEPS" :key="s.key" :text="s.label">
        <button
          type="button"
          class="h-1 flex-1 rounded-full transition-colors"
          :class="state(i) === 'todo' ? 'bg-surface-gray-3' : 'bg-surface-gray-7'"
          :aria-label="s.label"
          :disabled="!canChangeStep || i > imp.step"
          @click="go(i)"
        />
      </Tooltip>
    </div>
  </div>
</template>

