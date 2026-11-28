<script setup>
/**
 * The card that ends an import, for a spreadsheet and for ERPNext alike: an icon, what happened,
 * one line on what it means, and the next actions (primary last) in the slot.
 */
import { computed } from 'vue'

const props = defineProps({
  // Products that went live after Publish all; null before publishing.
  published: { type: Number, default: null },
  // The run itself was refused or stopped. Both import sources end on this one card either way, so a
  // failure has the same layout, margins and button order (Close, then the way back) as a success.
  failed: { type: Boolean, default: false },
  title: { type: String, required: true },
  body: { type: String, default: '' },
})

// Green only when something went live: a Publish all that published nothing is not a success.
const tone = computed(() => {
  if (props.failed) return { icon: 'lucide-triangle-alert', surface: 'bg-surface-red-2 text-ink-red-7' }
  if (props.published === 0) return { icon: 'lucide-triangle-alert', surface: 'bg-surface-amber-2 text-ink-amber-7' }
  if (props.published != null) return { icon: 'lucide-circle-check', surface: 'bg-surface-green-2 text-ink-green-7' }
  return { icon: 'lucide-package-check', surface: 'bg-surface-gray-2 text-ink-gray-7' }
})
</script>

<template>
  <div class="rounded-6 border border-outline-gray-1 px-6 py-8 text-center">
    <div class="mx-auto flex size-12 items-center justify-center rounded-full" :class="tone.surface">
      <span :class="[tone.icon, 'size-6']" aria-hidden="true" />
    </div>
    <h2 class="mt-4 text-xl-semibold text-ink-gray-9">{{ title }}</h2>
    <!-- text-pretty: centred, a one-word last line ("page.") reads as a stray. -->
    <p v-if="body" class="mx-auto mt-1.5 max-w-md text-pretty text-p-base text-ink-gray-6">{{ body }}</p>
    <slot name="details" />
    <div class="mt-6 flex flex-wrap items-center justify-center gap-2">
      <slot />
    </div>
  </div>
</template>
