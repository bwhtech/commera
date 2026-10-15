import { computed, shallowRef } from 'vue'

// Settings is a dialog *and* a URL. The route renders nothing (see router.js): the page it
// was opened over stays mounted behind it.
export const SETTINGS_ROUTE_NAME = 'Settings'

export const DEFAULT_SETTINGS_TAB = 'general'

// Handed over by router.js rather than imported: importing it back would be a cycle.
let router = null

// The last location that was not the dialog; null when the URL was pasted cold.
const backgroundRoute = shallowRef(null)

export function attachSettingsRouter(instance) {
  router = instance
  router.afterEach((to) => {
    if (to.name !== SETTINGS_ROUTE_NAME) backgroundRoute.value = to
  })
}

function pickedTab() {
  const location = router.currentRoute.value
  return (location.name === SETTINGS_ROUTE_NAME && location.params.tab) || ''
}

function currentTab() {
  return pickedTab() || DEFAULT_SETTINGS_TAB
}

// Plain getters, not `reactive()`: they read router.currentRoute, which is a ref, so anything
// touching them tracks the navigation itself.
export const settings = {
  get open() {
    return router.currentRoute.value.name === SETTINGS_ROUTE_NAME
  },
  set open(shouldBeOpen) {
    if (shouldBeOpen === settings.open) return
    if (shouldBeOpen) openSettings(currentTab())
    else closeSettings()
  },
  get tab() {
    return currentTab()
  },
  get pickedTab() {
    return pickedTab()
  },
  set tab(tab) {
    // reka-ui's TabsRoot writes this model back as it mounts, which without the open guard
    // would navigate to /settings/general over a cold link to /settings/payments.
    if (!settings.open || tab === pickedTab()) return
    // replace, not push: Back closes the dialog rather than stepping back through tabs.
    router.replace({ name: SETTINGS_ROUTE_NAME, params: { tab } })
  },
}

// What the shell and the page behind the dialog must keep seeing, rather than /settings/*.
export const visibleRoute = computed(() =>
  settings.open && backgroundRoute.value ? backgroundRoute.value : router.currentRoute.value,
)

// An unknown tab is normalised by the route record's beforeEnter.
export function openSettings(tab) {
  router.push({ name: SETTINGS_ROUTE_NAME, params: { tab } })
}

// push, not back(): a cold-opened link has no history inside the app.
export function closeSettings() {
  router.push(backgroundRoute.value?.fullPath ?? '/')
}
