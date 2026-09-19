<script setup>
import { computed } from 'vue'
import { Button } from 'frappe-ui'
import { reopenSetup, setupDismissed, useSetupSteps } from '../../ia/firstRun'

const { steps, settingUp } = useSetupSteps()

const doneCount = computed(() => steps.value.filter((step) => step.done).length)
</script>

<template>
  <div
    v-if="settingUp && setupDismissed"
    class="flex flex-col gap-3 rounded-4 bg-surface-elevation-2 px-3 py-2.5 shadow-sm"
  >
    <div class="inline-flex gap-2 text-ink-gray-9">
      <span class="lucide-circle-check-big my-0.5 size-4 shrink-0" aria-hidden="true" />
      <div class="flex flex-col gap-0.5 text-p-sm">
        <p class="font-medium">Getting started</p>
        <p class="text-ink-gray-7">{{ `${doneCount}/${steps.length} steps` }}</p>
      </div>
    </div>
    <Button
      :label="doneCount === 0 ? 'Start now' : 'Continue'"
      icon-left="lucide-chevrons-right"
      @click="reopenSetup"
    />
  </div>
</template>
