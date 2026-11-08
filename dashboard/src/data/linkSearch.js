import { computed, onScopeDispose, ref, watch } from 'vue'
import { useAdminRead } from './api'

const SEARCH_DEBOUNCE_MS = 300

// Server-side search behind a Combobox: the endpoint decides what matches, not the client.
export function useLinkSearch(path, extraParams = () => ({}), committedValue = () => null) {
  const open = ref(false)
  const query = ref('')
  const searchText = ref('')

  // In the combobox's input mode the query IS the value display, so only a genuinely
  // different query counts as a search.
  const typed = computed(() => (open.value && query.value !== committedValue() ? query.value : ''))

  let debounceTimer = null
  watch(typed, (value) => {
    clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      searchText.value = value
    }, SEARCH_DEBOUNCE_MS)
  })
  // A keystroke just before the picker unmounts would otherwise fire into a dead component's read.
  onScopeDispose(() => clearTimeout(debounceTimer))

  const results = useAdminRead(path, {
    params: () => ({ ...extraParams(), search_text: searchText.value }),
    refetch: true,
  })

  return { open, query, results }
}
