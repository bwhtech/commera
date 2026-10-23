<script setup>
import { ref } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  collapsible: { type: Boolean, default: false },
  summary: { type: String, default: '' },
  defaultOpen: { type: Boolean, default: false },
})

const open = ref(!props.collapsible || props.defaultOpen)
</script>

<template>
  <section class="rounded-5 border border-outline-gray-1">
    <component
      :is="collapsible ? 'button' : 'div'"
      :type="collapsible ? 'button' : undefined"
      class="flex w-full items-start gap-3 p-4 text-left"
      :class="{ 'hover:bg-surface-gray-1 rounded-5': collapsible }"
      :aria-expanded="collapsible ? open : undefined"
      @click="collapsible && (open = !open)"
    >
      <div class="min-w-0 flex-1">
        <h2 class="text-base-semibold text-ink-gray-8">{{ title }}</h2>
        <p v-if="collapsible && !open && summary" class="mt-0.5 truncate text-p-sm text-ink-gray-6">{{ summary }}</p>
        <p v-else-if="description" class="mt-0.5 text-p-sm text-ink-gray-5">{{ description }}</p>
      </div>
      <span
        v-if="collapsible"
        class="lucide-chevron-down mt-0.5 size-4 shrink-0 text-ink-gray-5 transition-transform"
        :class="{ 'rotate-180': open }"
        aria-hidden="true"
      />
    </component>
    <div v-if="open" class="space-y-4 px-4 pb-4">
      <slot />
    </div>
  </section>
</template>
