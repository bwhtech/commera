import { computed, ref } from 'vue'
import { createAdminCaller } from './adminCaller'
import { wasAborted } from './api'
import { setStorefrontLanguages } from './boot'
import { toBootLanguages } from './languageList'
import { singleFlight } from '../utils/sequence'

// Every write answers with the whole screen, which is adopted as-is, and the boot list the
// theme editors read is rebuilt from it.

const screen = ref(null)
const loadError = ref(null)
let loaded = false

const { attempt, call, loading } = createAdminCaller('storefront_languages.')

const languages = computed(() => screen.value?.languages ?? [])
const defaultLanguage = computed(() => screen.value?.default_language ?? '')
const maxLanguages = computed(() => screen.value?.max_languages ?? 20)
const isAtLimit = computed(() => languages.value.length >= maxLanguages.value)

async function load() {
  const { data, error } = await attempt('get_storefront_languages')
  if (wasAborted(error)) return
  loadError.value = error
  if (data) adopt(data)
  if (data) loaded = true
}

const loadOnce = singleFlight(async () => {
  if (!loaded) await load()
})

// createAdminCaller has one request per method, so two quick moves would abort each other.
// Chained, each write gets its own request and the server sees them in click order.
let queue = Promise.resolve()

// Run a write and adopt the screen it returns, or null when the server refused it.
function mutate(method, params = {}) {
  const result = queue.then(async () => {
    const data = await call(method, params)
    if (data) adopt(data)
    return data
  })
  queue = result.catch(() => {})
  return result
}

function adopt(data) {
  screen.value = data
  setStorefrontLanguages(toBootLanguages(data))
}

export { languagePrefix } from './languageList'

export const storefrontLanguageSettings = {
  screen,
  loadError,
  loading,
  languages,
  defaultLanguage,
  maxLanguages,
  isAtLimit,
  load,
  loadOnce,
  mutate,
}
