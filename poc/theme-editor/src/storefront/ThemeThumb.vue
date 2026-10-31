<script setup>
// A theme's thumbnail. Its two colours are the theme's own (data, not
// styling), which is why this binds :style.
defineProps({ theme: { type: Object, required: true }, size: { type: String, default: 'md' } })
</script>

<template>
  <div
    class="relative shrink-0 overflow-hidden rounded border border-outline-gray-1"
    :class="size === 'lg' ? 'h-28 w-44' : 'h-14 w-20'"
    :style="{ background: `linear-gradient(135deg, ${theme.colours[0]}, ${theme.colours[1]})` }"
  >
    <span
      v-if="theme.kind === 'builder'"
      class="absolute bottom-1 left-1 rounded bg-white px-1 text-xs font-medium text-gray-900 shadow-sm"
    >Builder</span>
  </div>
</template>
