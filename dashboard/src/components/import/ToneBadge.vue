<script setup>
/**
 * A gray subtle Badge whose icon carries the tone: a Ready, Warning or Skipped row, a column to check.
 * frappe-ui's amber subtle Badge is amber-7 on amber-2, 3.55:1 in light mode, under AA for its 12px
 * text, so the words stay gray-6 on gray-2 (7:1 light, 5.1:1 dark) and only the icon is colored,
 * which needs 3:1. One look for all three tones, so a Warning never reads louder than a Skipped.
 */
import { computed } from 'vue'
import { Badge } from 'frappe-ui'

const TONES = {
  ready: 'lucide-circle-check text-ink-green-7',
  warning: 'lucide-triangle-alert text-ink-amber-7',
  error: 'lucide-circle-x text-ink-red-7',
}

const props = defineProps({
  label: { type: String, required: true },
  tone: { type: String, default: 'warning', validator: (tone) => ['ready', 'warning', 'error'].includes(tone) },
})

const icon = computed(() => TONES[props.tone])
</script>

<template>
  <Badge :label="label" theme="gray" variant="subtle">
    <template #prefix><span :class="[icon, 'size-3']" aria-hidden="true" /></template>
  </Badge>
</template>
