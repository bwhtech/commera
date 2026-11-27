<script setup>
defineProps({
  title: { type: String, default: '' },
  hint: { type: String, default: '' },
})
</script>

<!-- The one frame every product-page section wears, matching the Options and Variants cards.
     Basics leaves the title out: its fields are labelled and need no heading above them. -->
<template>
  <section class="rounded-5 border border-outline-gray-1">
    <div v-if="title" class="flex flex-wrap items-start justify-between gap-2 px-4 py-3">
      <div class="min-w-0">
        <h2 class="text-lg-semibold text-ink-gray-8">{{ title }}</h2>
        <p v-if="hint" class="mt-1 text-p-sm text-ink-gray-5">{{ hint }}</p>
      </div>
      <div v-if="$slots.actions" class="flex shrink-0 items-center gap-2">
        <slot name="actions" />
      </div>
    </div>
    <div v-if="$slots.default" class="px-4 py-4" :class="{ 'border-t border-outline-gray-1': title }">
      <slot />
    </div>
  </section>
</template>
