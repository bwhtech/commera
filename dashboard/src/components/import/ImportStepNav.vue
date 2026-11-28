<script setup>
import { Tooltip } from 'frappe-ui'
import { canChangeStep, imp, steps } from '../../data/importFlow'
import { __ } from '../../data/translation'

// Only steps you have already reached are clickable, and none while a step is waiting on the
// server or after the import landed (see importPhase.js).
function goTo(index) {
  if (canChangeStep.value && index <= imp.step) imp.step = index
}
</script>

<template>
  <!-- A nav of buttons, not a progressbar: ARIA makes a progressbar's children presentational, which
       hid every "go to step" button from a screen reader. The dialog's description already reads
       "Step 3 of 6 · …", so the position needs no second announcement here. -->
  <nav :aria-label="__('Import steps')">
    <!-- Each button is 24px tall (WCAG 2.5.8's minimum target) around a 4px bar. -my-2.5 hands the
         10px above and below the bar back to the header, so the strip still sits where the 4px bar
         did. Recheck the pair if the bar's height changes. -->
    <ol class="-my-2.5 flex gap-1">
      <li v-for="(step, index) in steps" :key="step.key" class="flex-1">
        <Tooltip :text="step.label">
          <button
            type="button"
            class="flex h-6 w-full items-center rounded-4 focus-visible:focus-ring disabled:cursor-default"
            :aria-label="__('Step {0}: {1}', [index + 1, step.label])"
            :aria-current="index === imp.step ? 'step' : undefined"
            :disabled="!canChangeStep || index > imp.step"
            @click="goTo(index)"
          >
            <span
              class="h-1 w-full rounded-full transition-colors"
              :class="index > imp.step ? 'bg-surface-gray-3' : 'bg-surface-gray-7'"
              aria-hidden="true"
            />
          </button>
        </Tooltip>
      </li>
    </ol>
  </nav>
</template>
