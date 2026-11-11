<script setup>
defineProps({
  // missing or outdated
  status: { type: String, required: true },
})

const COLOURS = {
  missing: 'bg-surface-red-7',
  outdated: 'bg-surface-amber-7',
}
</script>

<template>
  <span class="size-2 shrink-0 rounded-full" :class="COLOURS[status]" aria-hidden="true" />
</template>
