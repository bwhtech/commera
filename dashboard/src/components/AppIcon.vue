<script setup>
defineProps({
  src: { type: String, required: true },
})
</script>

<template>
  <img :src="src" alt="" class="inline-block shrink-0 object-contain" aria-hidden="true" />
</template>
