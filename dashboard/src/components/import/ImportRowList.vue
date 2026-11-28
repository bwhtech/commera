<script setup>
/**
 * The lists under an import result: rows that were skipped, rows that came in with a warning, photos
 * that did not attach, ERPNext items that failed. Each entry is named first (the row and its product,
 * or the item) and explained under it, as NotPublishedList does, so every list below a result reads
 * the same way.
 */
const TONE_ICONS = {
  warning: 'lucide-triangle-alert text-ink-amber-7',
  error: 'lucide-circle-x text-ink-red-7',
}

defineProps({
  title: { type: String, required: true },
  // [{ key, name, message }]
  entries: { type: Array, required: true },
  tone: { type: String, default: 'error', validator: (tone) => ['warning', 'error'].includes(tone) },
  footer: { type: String, default: '' },
})
</script>

<template>
  <div class="rounded-5 border border-outline-gray-1">
    <div class="flex items-center gap-2 border-b border-outline-gray-1 px-4 py-3">
      <span :class="[TONE_ICONS[tone], 'size-4 shrink-0']" aria-hidden="true" />
      <h3 class="text-base-semibold text-ink-gray-8">{{ title }}</h3>
    </div>
    <ul v-scroll-fade class="max-h-56 divide-y divide-outline-gray-1 overflow-y-auto">
      <li v-for="entry in entries" :key="entry.key" class="px-4 py-2.5">
        <div class="break-words text-base tabular-nums text-ink-gray-8">{{ entry.name }}</div>
        <p class="text-pretty text-p-sm text-ink-gray-6">{{ entry.message }}</p>
      </li>
    </ul>
    <p v-if="footer" class="border-t border-outline-gray-1 px-4 py-2.5 text-p-sm text-ink-gray-6">{{ footer }}</p>
  </div>
</template>
