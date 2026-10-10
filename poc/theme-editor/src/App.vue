<script setup>
import { FrappeUIProvider } from 'frappe-ui'
</script>

<template>
  <FrappeUIProvider>
    <div class="h-screen w-full bg-surface-base text-ink-gray-9">
      <router-view />
    </div>
  </FrappeUIProvider>
</template>
