<script setup>
import StorefrontShell from './StorefrontShell.vue'

defineProps({ title: { type: String, required: true }, text: { type: String, required: true } })
</script>

<template>
  <StorefrontShell>
    <h1 class="text-2xl font-semibold text-ink-gray-9">{{ title }}</h1>
    <p class="mt-1 text-base text-ink-gray-6">{{ text }}</p>
    <p class="mt-6 rounded-lg border border-dashed border-outline-gray-3 p-6 text-sm text-ink-gray-5">Unchanged by this proposal; shown so the whole Storefront section is visible.</p>
  </StorefrontShell>
</template>
