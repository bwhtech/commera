import { ref } from 'vue'
import { createAdminCaller } from './adminCaller'

const { attempt, call } = createAdminCaller('translations.')

// The overview's answer feeds the overview page and the editor's language menu alike.
const overview = ref(null)
const overviewError = ref(null)

async function loadOverview() {
  const { data, error } = await attempt('get_overview')
  overviewError.value = error
  if (data) overview.value = data
  return data
}

export function useTranslationOverview() {
  return { overview, overviewError, loadOverview }
}

export function getItems(params) {
  return attempt('get_items', params)
}

export function searchTranslations(language, text) {
  return call('search_translations', { language, text })
}

// Resolves to the number saved, or null when the server refused the batch.
export function saveTranslations(language, translations) {
  return call('save_translations', { language, translations })
}
