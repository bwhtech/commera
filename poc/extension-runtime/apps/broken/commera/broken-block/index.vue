<script setup>
// Simulates a buggy extension: it throws while rendering. The host must show a
// failure card for this one extension and keep the rest of the page working.
throw new Error('this extension is deliberately broken')
</script>

<template>
  <div>never rendered</div>
</template>
