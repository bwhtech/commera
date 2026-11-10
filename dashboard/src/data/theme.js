import { ref } from 'vue'
import { createAdminCaller } from './adminCaller'

const themes = ref([])

// A refused read leaves `themes` empty, which reads as "this store has no themes"
// unless the failure is kept.
const loadError = ref(null)

const builderInstalled = ref(false)

const { attempt, call, loading } = createAdminCaller('theme.')

async function load() {
  const { data, error } = await attempt('get_editor_data')
  loadError.value = error
  if (!data) return
  themes.value = data.themes ?? []
  builderInstalled.value = Boolean(data.builder_installed)
}

async function activate(theme) {
  const data = await call('activate_theme', { theme })
  if (!data) return false
  themes.value = data.themes ?? []
  return true
}

// Both halves, so the dialog can show the refusal under its field.
function createBuilderTheme(themeName) {
  return attempt('create_builder_theme', { theme_name: themeName })
}

export function useTheme() {
  return { themes, loadError, loading, builderInstalled, load, activate, createBuilderTheme }
}
