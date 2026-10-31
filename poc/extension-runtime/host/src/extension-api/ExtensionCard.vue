<script setup>
defineProps({ title: { type: String, required: true } })
</script>

<template>
  <section class="rounded-5 border border-outline-gray-2">
    <header class="flex items-center justify-between border-b border-outline-gray-2 px-4 py-3">
      <h3 class="text-base font-semibold text-ink-gray-9">{{ title }}</h3>
      <slot name="actions" />
    </header>
    <div class="space-y-2 px-4 py-3 text-sm text-ink-gray-7">
      <slot />
    </div>
  </section>
</template>
