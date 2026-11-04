import { reactive, watch } from 'vue'

// The confirmed IA. What used to be a set of switchable axes is now settled:
// grouped sidebar, summary panel on the product, stock edited on the product.
// Light and dark are not in here: that is `useColorScheme`, driven from
// Settings → Appearance.
const DEFAULTS = {
  density: 60,
  sidebarCollapsed: false,
}

const STORAGE_KEY = 'commera:ui'

function load() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') }
  } catch {
    return { ...DEFAULTS }
  }
}

export const ia = reactive(load())

watch(
  ia,
  (value) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
    } catch {
      /* private mode — the app still works, it just won't persist */
    }
  },
  { immediate: true, deep: true },
)
