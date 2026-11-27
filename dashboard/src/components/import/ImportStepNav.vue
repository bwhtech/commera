<script setup>
import { computed } from 'vue'
import { Tooltip } from 'frappe-ui'
import { canChangeStep, imp, steps } from '../../data/importFlow'

const percent = computed(() => Math.round(((imp.step + 1) / steps.value.length) * 100))

// Only steps you have already reached are clickable, and none while a step is waiting on the
// server or after the import landed (see importPhase.js).
function goTo(index) {
  if (canChangeStep.value && index <= imp.step) imp.step = index
}
</script>

<template>
  <div class="flex items-center gap-3">
    <div class="flex flex-1 gap-1" role="progressbar" :aria-valuenow="percent">
      <Tooltip v-for="(step, index) in steps" :key="step.key" :text="step.label">
        <button
          type="button"
          class="h-1 flex-1 rounded-full transition-colors"
          :class="index > imp.step ? 'bg-surface-gray-3' : 'bg-surface-gray-7'"
          :aria-label="step.label"
          :disabled="!canChangeStep || index > imp.step"
          @click="goTo(index)"
        />
      </Tooltip>
    </div>
    <!-- Read out through the dialog's description (ImportDialog), which also names the step. -->
    <span class="shrink-0 text-sm tabular-nums text-ink-gray-5" aria-hidden="true">
      {{ __('Step {0} of {1}', [imp.step + 1, steps.length]) }}
    </span>
  </div>
</template>
