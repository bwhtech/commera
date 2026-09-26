<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { DesktopShell, FrappeUIProvider, Sidebar, SidebarItem, SidebarLabel } from 'frappe-ui'
import { navLinks } from './ia/extensions.js'

const route = useRoute()
const core = [
  { label: 'Overview', icon: 'lucide-layout-dashboard', to: '/' },
  { label: 'Order SO-1001', icon: 'lucide-shopping-bag', to: '/orders/SO-1001' },
]
const apps = computed(navLinks)
</script>

<template>
  <FrappeUIProvider>
    <div class="h-screen w-full bg-surface-base text-ink-gray-9">
      <DesktopShell>
        <template #sidebar>
          <Sidebar width="14rem" class="border-r border-outline-gray-1">
            <div class="flex h-full flex-col gap-1 p-2">
              <SidebarItem
                v-for="item in core"
                :key="item.to"
                v-bind="item"
                :active="route.path === item.to"
              />
              <template v-if="apps.length">
                <SidebarLabel divider>Apps</SidebarLabel>
                <SidebarItem
                  v-for="item in apps"
                  :key="item.to"
                  v-bind="item"
                  :active="route.path.startsWith(item.to)"
                  data-extension-nav
                />
              </template>
            </div>
          </Sidebar>
        </template>
        <router-view />
      </DesktopShell>
    </div>
  </FrappeUIProvider>
</template>
