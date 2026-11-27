<script setup>
import { computed, defineAsyncComponent, provide, ref, shallowReactive } from 'vue'
import { START_LOCATION, routeLocationKey } from 'vue-router'
import { FrappeUIProvider } from 'frappe-ui'
import { isAdmin } from './data/boot'
import { storeSetup } from './data/onboarding'
import { onboardingOpen } from './ia/onboarding'
import { visibleRoute } from './ia/settingsRoute'
import { useIsMobile } from './utils/useIsMobile'
import AppShell from './components/AppShell.vue'
import AppSettingsDialog from './components/settings/AppSettingsDialog.vue'
import SearchPalette from './components/SearchPalette.vue'
import ImportDialog from './components/import/ImportDialog.vue'
import AddProductDialog from './components/AddProductDialog.vue'
import LanguageDialog from './components/LanguageDialog.vue'

// frappe-ui ships MobileShell alongside DesktopShell rather than as a responsive variant,
// so the layout is picked per viewport. The phone bundle is lazy.
const isMobileViewport = useIsMobile()
const MobileLayout = defineAsyncComponent(() => import('./components/MobileLayout.vue'))
const Layout = computed(() => (isMobileViewport.value ? MobileLayout : AppShell))
// The page renders once, outside both shells, and is teleported into whichever one is up: swapping
// shells at the breakpoint would otherwise remount the page and drop whatever it held unsaved.
const pageOutlet = ref(null)
const isShellPage = computed(() => !onboardingOpen.value && !visibleRoute.value.meta.fullscreen)
const OnboardingFlow = defineAsyncComponent(() => import('./components/onboarding/OnboardingFlow.vue'))

// The add-product dialog reads collections and attributes as it mounts, which only exist once the
// store setup has made the company, so during onboarding it waits for that.
const canAddProducts = computed(() => !onboardingOpen.value || storeSetup.status === 'done')

// `<router-view :route>` does not override what `useRoute()` injects, so the same location
// goes under vue-router's own key or every page behind the dialog loses its params.
const shellRoute = {}
for (const key in START_LOCATION) {
  Object.defineProperty(shellRoute, key, { get: () => visibleRoute.value[key], enumerable: true })
}
provide(routeLocationKey, shallowReactive(shellRoute))
</script>

<template>
  <FrappeUIProvider>
    <!-- Onboarding replaces the shell rather than covering it: every screen behind it reads a
         company that does not exist yet on a fresh site. -->
    <OnboardingFlow v-if="onboardingOpen" />
    <router-view v-else-if="visibleRoute.meta.fullscreen" :route="visibleRoute" />
    <component :is="Layout" v-else>
      <div ref="pageOutlet" class="contents" />
    </component>
    <!-- Between shells (the phone one loads lazily) the page waits here, hidden but still mounted. -->
    <div v-if="isShellPage" hidden>
      <Teleport :to="pageOutlet" :disabled="!pageOutlet">
        <router-view :route="visibleRoute" />
      </Teleport>
    </div>

    <!-- One instance for the whole app, outside the layout so both shells reach
         them; opened from the workspace menu and the sidebar footer. Settings and search
         fetch as they mount, so they wait for onboarding; the products step opens the other two. -->
    <template v-if="isAdmin">
      <template v-if="!onboardingOpen">
        <AppSettingsDialog />
        <SearchPalette />
      </template>
      <ImportDialog />
      <AddProductDialog v-if="canAddProducts" />
    </template>
    <LanguageDialog />
  </FrappeUIProvider>
</template>

