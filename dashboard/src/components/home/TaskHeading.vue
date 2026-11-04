<script setup>
import { computed } from 'vue'
import { Button } from 'frappe-ui'

const props = defineProps({
  title: { type: String, required: true },
  done: { type: Number, required: true },
  total: { type: Number, required: true },
  dismissedCount: { type: Number, default: 0 },
})
defineEmits(['restore'])

// Listed rather than computed: Tailwind only generates class names it can read. Four tasks, five on Frappe Cloud.
const FILLS = {
  4: ['scale-x-0', 'scale-x-[0.25]', 'scale-x-50', 'scale-x-75', 'scale-x-100'],
  5: ['scale-x-0', 'scale-x-[0.2]', 'scale-x-[0.4]', 'scale-x-[0.6]', 'scale-x-[0.8]', 'scale-x-100'],
}
const fill = computed(() => FILLS[props.total]?.[props.done] ?? 'scale-x-0')
</script>

<template>
  <div class="mb-4 flex flex-wrap items-center gap-3">
    <h2 class="text-lg-semibold text-ink-gray-8">{{ title }}</h2>
    <div class="flex items-center gap-2 text-sm text-ink-gray-5">
      <div class="h-1.5 w-20 overflow-hidden rounded-full bg-surface-gray-2">
        <div
          class="h-full origin-left rounded-full bg-surface-gray-7 transition-transform duration-300 ease-in-out-strong motion-reduce:transition-none"
          :class="fill"
        />
      </div>
      <span class="tabular-nums">{{ done }} of {{ total }} done</span>
    </div>
    <Button
      v-if="dismissedCount"
      variant="ghost"
      size="sm"
      class="ml-auto"
      :label="`Show ${dismissedCount} dismissed`"
      @click="$emit('restore')"
    />
  </div>
</template>
