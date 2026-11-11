import { ref, watch } from 'vue'
import { createSequence } from '../utils/sequence.js'

// A record finished by a save keeps its place in the list until the filter, language or resource
// changes, so the merchant's place does not jump. `filter` is 'todo' or 'all'.
export function useTranslationItems(language, resource, filter, getItems) {
  const items = ref([])
  const total = ref(0)
  const toDoCount = ref(0)
  const nextCursor = ref(null)
  const loading = ref(false)
  const loadError = ref(null)
  const loaded = ref(false)
  const loads = createSequence()

  function params(extra = {}) {
    return { language: language.value, resource: resource.value, to_do: filter.value === 'todo' ? 1 : 0, ...extra }
  }

  async function load() {
    // The page is being left: the route no longer names a language and a resource.
    if (!language.value || !resource.value) return
    const ticket = loads.next()
    items.value = []
    nextCursor.value = null
    loading.value = true
    loaded.value = false
    loadError.value = null
    const { data, error } = await getItems(params())
    if (!loads.isLatest(ticket)) return
    loadError.value = error
    loaded.value = !error && Boolean(data)
    items.value = data?.items ?? []
    total.value = data?.total ?? 0
    toDoCount.value = data?.to_do ?? 0
    nextCursor.value = data?.next_cursor ?? null
    loading.value = false
  }

  async function loadMore() {
    if (!nextCursor.value || loading.value) return
    const ticket = loads.current()
    loading.value = true
    const { data, error } = await getItems(params({ cursor: nextCursor.value }))
    if (!loads.isLatest(ticket)) return
    loadError.value = error
    if (data) {
      items.value = [...items.value, ...data.items]
      nextCursor.value = data.next_cursor ?? null
    }
    loading.value = false
  }

  // One record as the server has it now, whether or not it is in the loaded list.
  async function fetchItem(name) {
    const ticket = loads.current()
    const { data, error } = await getItems(params({ record: name }))
    if (!loads.isLatest(ticket)) return null
    return { item: data?.items?.[0] ?? null, error }
  }

  // Reread records after a save, in place, and keep the to-do count in step with them.
  async function refresh(names) {
    const ticket = loads.current()
    const { data, error } = await getItems(params({ records: names }))
    if (error || !data) return
    const fresh = data.items
    if (!loads.isLatest(ticket)) return
    for (const item of fresh.filter(Boolean)) {
      const index = items.value.findIndex((listed) => listed.name === item.name)
      if (index === -1) continue
      toDoCount.value += Number(Boolean(item.to_do)) - Number(Boolean(items.value[index].to_do))
      items.value[index] = item
    }
    return fresh
  }

  watch([language, resource, filter], load, { immediate: true, flush: 'sync' })

  return { items, total, toDoCount, nextCursor, loading, loaded, loadError, load, loadMore, fetchItem, refresh }
}
