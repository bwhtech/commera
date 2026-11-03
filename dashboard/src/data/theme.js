import { ref } from 'vue'
import { createAdminCaller } from './adminCaller'

const themes = ref([])

// A refused read leaves `themes` empty, which reads as "this store has no themes"
// unless the failure is kept.
const loadError = ref(null)

const { attempt, call, loading } = createAdminCaller('theme.')

async function load() {
  const { data, error } = await attempt('get_editor_data')
  loadError.value = error
  if (data) themes.value = data.themes ?? []
}

async function activate(theme) {
  const data = await call('activate_theme', { theme })
  if (!data) return false
  themes.value = data.themes ?? []
  return true
}

export function useTheme() {
  return { themes, loadError, loading, load, activate }
}
