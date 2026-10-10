<script setup>
import { computed, defineAsyncComponent, provide, shallowReactive } from 'vue'
import { START_LOCATION, routeLocationKey } from 'vue-router'
import { FrappeUIProvider } from 'frappe-ui'
import { visibleRoute } from './ia/settingsRoute'
import { useIsMobile } from './utils/useIsMobile'
import AppShell from './components/AppShell.vue'
import AppSettingsDialog from './components/settings/AppSettingsDialog.vue'
import SearchPalette from './components/SearchPalette.vue'
import ImportDialog from './components/import/ImportDialog.vue'
import AddProductDialog from './components/AddProductDialog.vue'

// frappe-ui ships MobileShell alongside DesktopShell rather than as a responsive variant,
// so the layout is picked per viewport. The phone bundle is lazy.
const isMobileViewport = useIsMobile()
const MobileLayout = defineAsyncComponent(() => import('./components/MobileLayout.vue'))
const Layout = computed(() => (isMobileViewport.value ? MobileLayout : AppShell))

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
    <component :is="Layout">
      <router-view :route="visibleRoute" />
    </component>

    <!-- One instance for the whole app, outside the layout so both shells reach
         them; opened from the workspace menu and the sidebar footer. -->
    <AppSettingsDialog />
    <SearchPalette />
    <ImportDialog />
    <AddProductDialog />
  </FrappeUIProvider>
</template>

