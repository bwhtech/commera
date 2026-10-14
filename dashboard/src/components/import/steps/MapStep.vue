<script setup>
import { computed } from 'vue'
import { Alert, Badge, Button, Select } from 'frappe-ui'
import { REQUIRED_FIELDS, TARGET_FIELDS, applyValidation, imp, validateImportAction } from '../../../data/importFlow'
import CoachTip from '../CoachTip.vue'

const mapped = computed(() => Object.values(imp.mapping).filter(Boolean).length)
const skipped = computed(() => imp.headers.length - mapped.value)

const missing = computed(() => REQUIRED_FIELDS.filter((f) => !Object.values(imp.mapping).includes(f)))

const labelFor = (v) => TARGET_FIELDS.find((f) => f.value === v)?.label ?? ''

const confidenceTheme = { high: 'green', medium: 'orange', low: 'gray', none: 'gray' }
const confidenceLabel = { high: 'Sure', medium: 'Likely', low: 'Guess', none: 'No match' }

async function recheck() {
  try {
    await validateImportAction.submit({ file_url: imp.fileUrl, column_mapping: { ...imp.mapping } })
  } catch {
    return
  }
  applyValidation(validateImportAction.data)
}

async function resetToSuggested() {
  try {
    await validateImportAction.submit({ file_url: imp.fileUrl })
  } catch {
    return
  }
  applyValidation(validateImportAction.data)
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-start gap-4">
      <div class="min-w-0 flex-1">
        <h2 class="text-xl text-ink-gray-9">Match your columns</h2>
        <p class="mt-1 text-p-base text-ink-gray-6">
          We matched {{ mapped }} of {{ imp.headers.length }} columns for you. Change anything that
          looks wrong, then re-check.
        </p>
      </div>
      <Button
        class="shrink-0"
        variant="subtle"
        icon-left="lucide-wand-sparkles"
        label="Use suggestions"
        :loading="validateImportAction.loading"
        @click="resetToSuggested"
      />
    </div>

    <Alert v-if="missing.length" theme="red" :title="'Still needed: ' + missing.map(labelFor).join(', ')" />

    <!-- Three columns whose middle cell is a Select: below ~30rem they crush each
         other rather than the row scrolling, so the card scrolls its own content. -->
    <div class="overflow-hidden rounded-5 border border-outline-gray-1">
      <div class="overflow-x-auto">
        <div
          class="grid min-w-[30rem] grid-cols-[minmax(0,1fr)_minmax(0,1fr)_6rem] gap-4 border-b border-outline-gray-1 bg-surface-gray-1 px-5 py-3"
        >
          <span class="text-sm text-ink-gray-5">Column in your file</span>
          <span class="text-sm text-ink-gray-5">Goes into</span>
          <span class="text-right text-sm text-ink-gray-5">Match</span>
        </div>

        <div class="min-w-[30rem] divide-y divide-outline-gray-1">
          <div
            v-for="h in imp.headers"
            :key="h"
            class="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_6rem] items-center gap-4 px-5 py-3.5"
          >
            <div class="min-w-0">
              <div class="truncate text-base text-ink-gray-8">{{ h }}</div>
            </div>

            <div class="flex items-center gap-2">
              <span class="lucide-arrow-right size-3.5 shrink-0 text-ink-gray-4" aria-hidden="true" />
              <Select v-model="imp.mapping[h]" :options="TARGET_FIELDS" class="min-w-0 flex-1" />
            </div>

            <div class="flex justify-end">
              <Badge
                :label="imp.mapping[h] ? confidenceLabel[imp.confidence[h]] : 'Skipped'"
                :theme="imp.mapping[h] ? confidenceTheme[imp.confidence[h]] : 'gray'"
                variant="subtle"
              />
            </div>
          </div>
        </div>
      </div>

      <div class="flex items-center gap-4 border-t border-outline-gray-1 bg-surface-gray-1 px-4 py-2.5">
        <span class="text-sm text-ink-gray-6">{{ mapped }} columns mapped</span>
        <span class="text-sm text-ink-gray-5">{{ skipped }} skipped</span>
        <Button
          class="ml-auto"
          variant="subtle"
          size="sm"
          label="Re-check"
          :disabled="!!missing.length"
          :loading="validateImportAction.loading"
          @click="recheck"
        />
      </div>
    </div>

    <CoachTip
      title="Skipping a column is safe"
      text="Anything you leave out never reaches your catalogue, and your own file stays untouched."
    />
  </div>
</template>

