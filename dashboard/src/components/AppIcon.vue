<script setup>
import { computed } from 'vue'

const props = defineProps({
  src: { type: String, required: true },
})

// The URL is data, not styling, so it rides in a custom property that the static mask classes read.
// The mask paints the SVG in currentColor, which is what keeps an app's logo one colour in both themes.
const maskSource = computed(() => ({ '--app-icon': `url("${props.src}")` }))
</script>

<template>
  <span
    class="inline-block shrink-0 bg-current [mask-image:var(--app-icon)] [mask-position:center] [mask-repeat:no-repeat] [mask-size:contain]"
    :style="maskSource"
    aria-hidden="true"
  />
</template>
