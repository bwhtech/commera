import { computed, ref } from 'vue'

export function createLanguageSettingsStore({ attempt, call, loading, wasAborted, onAdopt }) {
  const screen = ref(null)
  const loadError = ref(null)
  const languages = computed(() => screen.value?.languages ?? [])
  const defaultLanguage = computed(() => screen.value?.default_language ?? '')
  const maxLanguages = computed(() => screen.value?.max_languages ?? 20)
  const isAtLimit = computed(() => languages.value.length >= maxLanguages.value)
  let revision = 0
  let pendingWrites = 0
  let queue = Promise.resolve()

  async function load() {
    // Reads overlapping a write may contain its old snapshot, even if they finish last.
    if (pendingWrites) return
    const ticket = ++revision
    const { data, error } = await attempt('get_storefront_languages')
    if (ticket !== revision || wasAborted(error)) return
    loadError.value = error
    if (data) adopt(data)
  }

  function mutate(method, params = {}) {
    revision += 1
    pendingWrites += 1
    // One request per method would abort rapid repeated moves; serialize every write.
    const result = queue.then(async () => {
      try {
        const data = await call(method, params)
        if (data) adopt(data)
        return data
      } finally {
        pendingWrites -= 1
      }
    })
    queue = result.catch(() => {})
    return result
  }

  function adopt(data) {
    screen.value = data
    loadError.value = null
    onAdopt(data)
  }

  return { screen, loadError, loading, languages, defaultLanguage, maxLanguages, isAtLimit, load, mutate }
}
