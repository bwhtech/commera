<script setup>
import { TabButtons } from 'frappe-ui'
import { useRoute } from 'vue-router'

// Storefront section tabs, as in the dashboard's sidebar (Theme, Pages).
const route = useRoute()
</script>

<template>
  <TabButtons
    :model-value="route.path === '/pages' ? 'pages' : 'themes'"
    :options="[
      { value: 'themes', label: 'Theme', route: '/' },
      { value: 'pages', label: 'Pages', route: '/pages' },
    ]"
  />
</template>
