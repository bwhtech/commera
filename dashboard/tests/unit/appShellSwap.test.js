import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as Vue from 'vue'
import { findNode, loadComponent, mount } from '../helpers/mountVue.js'

const shellStub = (type) => ({ render() { return Vue.h(type, this.$slots.default?.()) } })
const nothing = { render: () => null }

function renderApp() {
  const isMobile = Vue.ref(false)
  const counts = { mounted: 0, unmounted: 0 }
  const Page = {
    setup() {
      Vue.onMounted(() => counts.mounted++)
      Vue.onUnmounted(() => counts.unmounted++)
      return () => Vue.h('page')
    },
  }
  const App = loadComponent('App', {
    // The phone shell is lazy and <router-view> is the router's: both resolve to stubs here.
    Vue: {
      ...Vue,
      defineAsyncComponent: (loader) => (String(loader).includes('MobileLayout') ? shellStub('mobile-shell') : nothing),
      resolveComponent: (name) => (name === 'router-view' ? Page : Vue.resolveComponent(name)),
    },
    START_LOCATION: {},
    routeLocationKey: Symbol('route'),
    FrappeUIProvider: shellStub('provider'),
    isAdmin: false,
    storeSetup: {},
    onboardingOpen: Vue.ref(false),
    visibleRoute: Vue.computed(() => ({ meta: {} })),
    useIsMobile: () => isMobile,
    AppShell: shellStub('desktop-shell'),
    AppSettingsDialog: nothing,
    SearchPalette: nothing,
    ImportDialog: nothing,
    AddProductDialog: nothing,
    LanguageDialog: nothing,
  })
  const { root } = mount({ render: () => Vue.h(App) })
  const shellOf = () => {
    const page = findNode(root, (node) => node.type === 'page')
    let node = page?.parent
    while (node && !node.type.endsWith('-shell')) node = node.parent
    return node?.type
  }
  return { isMobile, counts, shellOf }
}

test('the page moves into the shell the viewport picks without remounting', async () => {
  const { isMobile, counts, shellOf } = renderApp()
  await Vue.nextTick()
  assert.equal(shellOf(), 'desktop-shell')

  isMobile.value = true
  await Vue.nextTick()
  await Vue.nextTick()
  assert.equal(shellOf(), 'mobile-shell')

  isMobile.value = false
  await Vue.nextTick()
  await Vue.nextTick()
  assert.equal(shellOf(), 'desktop-shell')
  assert.deepEqual(counts, { mounted: 1, unmounted: 0 })
})
