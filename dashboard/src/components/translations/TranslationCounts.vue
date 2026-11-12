<script setup>
import TranslationStatusDot from './TranslationStatusDot.vue'
import { isEmptyResource } from '../../data/translationStatus'

defineProps({
  // { missing, outdated, current }
  counts: { type: Object, required: true },
})
</script>

<template>
  <span v-if="isEmptyResource(counts)" class="text-sm text-ink-gray-5">{{ __('Nothing to translate') }}</span>
  <span v-else-if="!counts.missing && !counts.outdated" class="flex items-center gap-1.5 text-sm text-ink-gray-5">
    <span class="lucide-check size-3.5 text-ink-green-5" aria-hidden="true" />
    {{ __('Done') }}
  </span>
  <span v-else class="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-sm tabular-nums text-ink-gray-8">
    <span v-if="counts.missing" class="flex items-center gap-1.5">
      <TranslationStatusDot status="missing" />
      {{ __('{0} missing', [counts.missing]) }}
    </span>
    <span v-if="counts.outdated" class="flex items-center gap-1.5">
      <TranslationStatusDot status="outdated" />
      {{ __('{0} outdated', [counts.outdated]) }}
    </span>
  </span>
</template>
