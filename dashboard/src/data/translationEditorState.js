import { computed, ref, watch } from 'vue'

export async function savePending(pending, submit) {
  const submitted = { ...pending }
  const saved = await submit(submitted)
  if (saved !== null) {
    for (const [key, value] of Object.entries(submitted)) {
      if (pending[key] === value) delete pending[key]
    }
  }
  return saved
}

export function useOpenedTranslation(language, resource) {
  const context = computed(() => JSON.stringify([language.value, resource.value]))
  const cached = ref(null)
  const itemKey = (name) => JSON.stringify([language.value, resource.value, name])
  const openedItem = computed({
    get: () => cached.value?.key === itemKey(cached.value?.item.name) ? cached.value.item : null,
    set: (item) => { cached.value = item ? { key: itemKey(item.name), item } : null },
  })
  const unknownName = ref('')
  let request = 0
  watch(context, () => {
    request += 1
    openedItem.value = null
    unknownName.value = ''
  }, { flush: 'sync' })

  async function open(name, fetchItem) {
    const ticket = ++request
    const key = context.value
    const item = await fetchItem(name)
    if (ticket !== request || key !== context.value) return
    if (item) openedItem.value = item
    else unknownName.value = name
  }

  return { openedItem, unknownName, open }
}
