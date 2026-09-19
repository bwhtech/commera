<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { DesktopShell, ScrollArea, Sidebar, SidebarHeader } from 'frappe-ui'
import { activeNavTarget, productName, sections } from '../ia/nav'
import logoUrl from '../assets/commera.svg'
import { openSettings } from '../ia/settings'
import { useAdminRead, useMethodAction } from '../data/api'
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

// The storefront is served by this same site, so it is the origin's root — a
// bare '/' redirects to the shopper's language.
function openStorefront() {
  window.open('/', '_blank', 'noopener')
}

const logoutAction = useMethodAction('logout', { quiet: true })

// `location.replace` rather than a router push: the session cookie is gone
// server-side, so the shell in memory is authenticated against nothing and
// every subsequent read would 403 behind a screen that still looks logged in.
async function logout() {
  // The redirect runs either way: a logout that failed still leaves a shell whose
  // session may be gone, and stranding the merchant on it is worse than sending
  // them to a login page they can retry from.
  try {
    await logoutAction.submit()
  } finally {
    window.location.replace('/login')
  }
}

// The workspace header is the dropdown: it names the store and gets you to the
// things that are about the account, not about the page you are on.
const headerMenu = [
  { label: 'Settings', icon: 'lucide-settings', onClick: () => openSettings('general') },
  { label: 'Appearance', icon: 'lucide-sun-moon', onClick: () => openSettings('appearance') },
  { label: 'View storefront', icon: 'lucide-external-link', onClick: openStorefront },
  { label: 'Log out', icon: 'lucide-log-out', onClick: logout },
]
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
            <ScrollArea class="min-h-0 flex-1" viewport-class="pt-1 pb-10">
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

