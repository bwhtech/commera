<script setup>
import { useRoute, useRouter } from 'vue-router'
import DashboardFrame from '../variations/DashboardFrame.vue'

// The dashboard's Storefront section, reorganised the way Shopify's Online
// Store is: Themes (the core), Pages (content), Navigation, Preferences.
const route = useRoute()
const router = useRouter()
const items = [
  { key: 'themes', label: 'Themes', icon: 'lucide-palette' },
  { key: 'pages', label: 'Pages', icon: 'lucide-file-text' },
  { key: 'navigation', label: 'Navigation', icon: 'lucide-list-tree' },
  { key: 'preferences', label: 'Preferences', icon: 'lucide-sliders-horizontal' },
]
const active = () => items.find((item) => route.path.startsWith(`/storefront/${item.key}`))?.key ?? 'themes'
</script>

<template>
  <DashboardFrame :active="active()" :items="items" @navigate="(key) => router.push(`/storefront/${key}`)">
    <template v-if="$slots.bare" #bare><slot name="bare" /></template>
    <slot />
  </DashboardFrame>
</template>
