<script setup>
defineProps({
  image: { type: String, default: null },
  size: { type: String, default: 'size-8' },
})
</script>

<template>
  <img
    v-if="image"
    :src="image"
    class="shrink-0 rounded-4 bg-surface-gray-2 object-cover"
    :class="size"
    alt=""
  />
  <div
    v-else
    class="grid shrink-0 place-content-center rounded-4 bg-surface-gray-2 text-ink-gray-4"
    :class="size"
    aria-hidden="true"
  >
    <span class="lucide-image size-4" />
  </div>
</template>
