<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { DesktopShell, ScrollArea, Sidebar, SidebarHeader } from 'frappe-ui'
import { activeNavTarget, productName, sections } from '../ia/nav'
import logoUrl from '../assets/commera.svg'
import { useAccountMenu } from '../data/account'
import { useAdminRead } from '../data/api'
import NavSection from './NavSection.vue'
import SetupBanner from './firstrun/SetupBanner.vue'

const route = useRoute()

const activeTarget = computed(() => activeNavTarget(route.path))

// The store's own name, read once for the shell. Reading Commera Settings
// takes a permission not every member of staff holds, and this is a subtitle:
// a refusal leaves it blank, the way an unconfigured site does, rather than
// toasting an error over every page a picker or a cashier opens.
const storeSettings = useAdminRead('settings.get_store_settings', { quiet: true })

const storeName = computed(() => storeSettings.data?.store_name || null)

const headerMenu = useAccountMenu()
</script>

<template>
  <div class="h-screen w-full bg-surface-base text-ink-gray-9">
    <DesktopShell :scroll="!route.meta.split">
      <template #sidebar>
        <Sidebar width="14rem" class="border-r border-outline-gray-1">
          <div class="flex h-full flex-col p-2">
            <SidebarHeader :title="productName" :subtitle="storeName" :menu-items="headerMenu">
              <template #prefix>
                <img :src="logoUrl" alt="" class="h-full w-full object-cover" />
              </template>
            </SidebarHeader>
            <ScrollArea v-scroll-fade class="min-h-0 flex-1" viewport-class="pt-1 pb-10">
              <NavSection v-for="section in sections" :key="section.id" :section="section" :active-target="activeTarget" />
            </ScrollArea>
            <SetupBanner />
          </div>
        </Sidebar>
      </template>

      <slot />
    </DesktopShell>
  </div>
</template>

