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
       clip box, so the dot of whichever part starts a line falls outside it. Change the pair together.
       Each part is itself a flex row of dot + text: a part too long for one line then wraps inside its
       text box, so its second line starts under its first word, not back under the clipped dot. -->
  <div class="overflow-hidden">
    <div class="-ms-3 flex flex-wrap gap-y-0.5">
      <span v-for="(part, index) in parts" :key="index" class="flex min-w-0 items-baseline">
        <span class="w-3 shrink-0 text-center text-ink-gray-5" aria-hidden="true">·</span>
        <span class="min-w-0 break-words">
          <slot :part="part"><span :class="part.class">{{ part.label ?? part }}</span></slot>
        </span>
      </span>
    </div>
  </div>
</template>
