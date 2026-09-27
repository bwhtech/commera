<script setup>
import { Sidebar, SidebarItem, SidebarLabel } from 'frappe-ui'

// A stand-in for the dashboard shell, so each variation is judged where the
// merchant actually meets it: the Storefront section of the sidebar.
defineProps({
  active: { type: String, required: true },
  items: { type: Array, required: true }, // [{ key, label, icon }]
  variant: { type: String, required: true },
})
defineEmits(['navigate'])
</script>

<template>
  <div class="flex h-screen">
    <Sidebar width="14rem" class="border-r border-outline-gray-1">
      <div class="flex h-full flex-col gap-0.5 p-2">
        <div class="mb-2 px-2 py-1 text-base font-semibold text-ink-gray-9">Commera · {{ variant }}</div>
        <SidebarItem label="Overview" icon="lucide-layout-dashboard" />
        <SidebarItem label="Orders" icon="lucide-shopping-bag" />
        <SidebarItem label="Products" icon="lucide-package" />
        <SidebarLabel divider>Storefront</SidebarLabel>
        <SidebarItem
          v-for="item in items"
          :key="item.key"
          :label="item.label"
          :icon="item.icon"
          :active="active === item.key"
          :data-nav="item.key"
          @click="$emit('navigate', item.key)"
        />
      </div>
    </Sidebar>
    <main class="min-w-0 flex-1 overflow-y-auto">
      <div class="mx-auto max-w-3xl px-8 py-10"><slot /></div>
    </main>
  </div>
</template>
