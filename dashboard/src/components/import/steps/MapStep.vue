<script setup>
import { computed } from 'vue'
import { Alert, Badge, Button, Select } from 'frappe-ui'
import { trySubmit } from '../../../data/api'
import {
  REQUIRED_FIELDS,
  TARGET_FIELDS,
  applyValidation,
  beginPhase,
  endPhase,
  imp,
  isCurrentImport,
  validateImportAction,
} from '../../../data/importFlow'
import CoachTip from '../CoachTip.vue'
import { __ } from '../../../data/translation'

const mapped = computed(() => Object.values(imp.mapping).filter(Boolean).length)
const skipped = computed(() => imp.headers.length - mapped.value)

const missing = computed(() => REQUIRED_FIELDS.filter((f) => !Object.values(imp.mapping).includes(f)))

const labelFor = (v) => TARGET_FIELDS.find((f) => f.value === v)?.label ?? ''

const confidenceTheme = { high: 'green', medium: 'amber', low: 'gray', none: 'gray' }
const confidenceLabel = { high: __('Sure'), medium: __('Likely'), low: __('Guess'), none: __('No match') }

// Re-validating rewrites the counts Review shows and Import commits, so the step stays put until
// the answer is in.
async function validate(columnMapping) {
  const ticket = beginPhase('checking')
  if (ticket === null) return
  const params = columnMapping ? { file_url: imp.fileUrl, column_mapping: columnMapping } : { file_url: imp.fileUrl }
  const checked = await trySubmit(validateImportAction, params)
  if (checked && isCurrentImport(ticket)) applyValidation(validateImportAction.data)
  endPhase(ticket)
}

const recheck = () => validate({ ...imp.mapping })
const resetToSuggested = () => validate(null)
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-start gap-4">
      <div class="min-w-0 flex-1">
        <h2 class="text-xl text-ink-gray-9">{{ __('Match your columns') }}</h2>
        <p class="mt-1 text-p-base text-ink-gray-6">
          {{ __('We matched {0} of {1} columns for you. Change anything that looks wrong, then re-check.', [mapped, imp.headers.length]) }}
        </p>
      </div>
      <Button
        class="shrink-0"
        variant="subtle"
        icon-left="lucide-wand-sparkles"
        :label="__('Use suggestions')"
        :loading="imp.phase === 'checking'"
        @click="resetToSuggested"
      />
    </div>

    <Alert v-if="missing.length" theme="red" :title="__('Still needed: {0}', [missing.map(labelFor).join(', ')])" />

    <!-- Three columns whose middle cell is a Select: below ~30rem they crush each
         other rather than the row scrolling, so the card scrolls its own content. -->
    <div class="overflow-hidden rounded-5 border border-outline-gray-1">
      <div class="overflow-x-auto">
        <div
          class="grid min-w-[30rem] grid-cols-[minmax(0,1fr)_minmax(0,1fr)_6rem] gap-4 border-b border-outline-gray-1 bg-surface-gray-1 px-5 py-3"
        >
          <span class="text-sm text-ink-gray-5">{{ __('Column in your file') }}</span>
          <span class="text-sm text-ink-gray-5">{{ __('Goes into') }}</span>
          <span class="text-end text-sm text-ink-gray-5">{{ __('Match') }}</span>
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
              <span class="lucide-arrow-right size-3.5 shrink-0 text-ink-gray-4 rtl:-scale-x-100" aria-hidden="true" />
              <Select v-model="imp.mapping[h]" :options="TARGET_FIELDS" class="min-w-0 flex-1" />
            </div>

            <div class="flex justify-end">
              <Badge
                :label="imp.mapping[h] ? confidenceLabel[imp.confidence[h]] : __('Skipped')"
                :theme="imp.mapping[h] ? confidenceTheme[imp.confidence[h]] : 'gray'"
                variant="subtle"
              />
            </div>
          </div>
        </div>
      </div>

      <div class="flex items-center gap-4 border-t border-outline-gray-1 bg-surface-gray-1 px-4 py-2.5">
        <span class="text-sm text-ink-gray-6">{{ __('{0} columns mapped', [mapped]) }}</span>
        <span class="text-sm text-ink-gray-5">{{ __('{0} skipped', [skipped]) }}</span>
        <Button
          class="ms-auto"
          variant="subtle"
          size="sm"
          :label="__('Re-check')"
          :disabled="!!missing.length"
          :loading="imp.phase === 'checking'"
          @click="recheck"
        />
      </div>
    </div>

    <CoachTip
      :title="__('Skipping a column is safe')"
      :text="__('Anything you leave out never reaches your catalogue, and your own file stays untouched.')"
    />
  </div>
</template>

