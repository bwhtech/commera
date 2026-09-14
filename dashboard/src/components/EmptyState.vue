<script setup>
import { computed } from 'vue'

const props = defineProps({
  icon: { type: String, default: 'lucide-inbox' },
  title: { type: String, required: true },
  description: { type: String, default: '' },
  // Inside a card — an Overview panel, a detail-page section — the full-height
  // state pushes the rest of the screen down, so the padding halves and the
  // icon loses its disc.
  compact: { type: Boolean, default: false },
  // A list emptied by a search or a tab filter is a different message from a
  // store that has nothing in it yet: "change the filters" is a lie on a fresh
  // install, which is the case this whole state exists for. Screens with
  // filters pass both sets and flip `filtered`.
  filtered: { type: Boolean, default: false },
  filteredIcon: { type: String, default: 'lucide-search-x' },
  filteredTitle: { type: String, default: '' },
  filteredDescription: { type: String, default: '' },
})

const showFiltered = computed(() => props.filtered && Boolean(props.filteredTitle))
const shownIcon = computed(() => (showFiltered.value ? props.filteredIcon : props.icon))
const shownTitle = computed(() => (showFiltered.value ? props.filteredTitle : props.title))
const shownDescription = computed(() =>
  showFiltered.value ? props.filteredDescription : props.description,
)
</script>

<template>
  <div
    class="flex flex-col items-center justify-center text-center"
    :class="compact ? 'gap-1.5 py-8' : 'gap-3 py-16'"
    role="status"
  >
    <div v-if="compact" class="text-ink-gray-4">
      <span :class="[shownIcon, 'size-5']" aria-hidden="true" />
    </div>
    <div v-else class="rounded-full bg-surface-gray-2 p-3 text-ink-gray-5">
      <span :class="[shownIcon, 'size-6']" aria-hidden="true" />
    </div>
    <p :class="compact ? 'text-base text-ink-gray-6' : 'text-base text-ink-gray-7'">
      {{ shownTitle }}
    </p>
    <p v-if="shownDescription" class="text-sm text-ink-gray-5">{{ shownDescription }}</p>
    <slot />
  </div>
</template>
