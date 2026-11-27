<script setup>
/**
 * Short facts joined by dots, as in "No options · ₹450 · 3 in stock", that wrap without a line
 * ever starting or ending on a dot. A part is a string or { label, class }.
 */
defineProps({
  parts: { type: Array, required: true },
})
</script>

<template>
  <!-- Every part carries its dot in front, and the row starts one dot-width (-ms-3 = w-3) before the
       clip box, so the dot of whichever part starts a line falls outside it. Change the pair together. -->
  <div class="overflow-hidden">
    <div class="-ms-3 flex flex-wrap gap-y-0.5">
      <span v-for="(part, index) in parts" :key="index" class="min-w-0">
        <span class="inline-block w-3 text-center text-ink-gray-4" aria-hidden="true">·</span>
        <slot :part="part"><span :class="part.class">{{ part.label ?? part }}</span></slot>
      </span>
    </div>
  </div>
</template>
