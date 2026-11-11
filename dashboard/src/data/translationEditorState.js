import { computed, ref, watch } from 'vue'

export function changePending(pending, key, field, value) {
  if (value === field.value && field.status !== 'outdated') delete pending[key]
  else pending[key] = value
}

export function useTranslationSave(pending, context) {
  const saving = ref(false)

  async function save(submit, refresh) {
    if (saving.value || !Object.keys(pending).length) return
    const startedIn = context.value
    saving.value = true
    try {
      const saved = await submit()
      if (saved === null || context.value !== startedIn) return
      const refreshed = await refresh(saved)
      if (refreshed !== false && context.value === startedIn) {
        for (const key of Object.keys(pending)) delete pending[key]
      }
    } finally {
      saving.value = false
    }
  }

  return { saving, save }
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
  const loadError = ref(null)
  const failedName = ref('')
  let request = 0
  watch(context, () => {
    request += 1
    openedItem.value = null
    unknownName.value = ''
    loadError.value = null
    failedName.value = ''
  }, { flush: 'sync' })

  async function open(name, fetchItem) {
    const ticket = ++request
    const key = context.value
    loadError.value = null
    failedName.value = ''
    unknownName.value = ''
    const result = await fetchItem(name)
    if (ticket !== request || key !== context.value) return
    if (result?.error) {
      loadError.value = result.error
      failedName.value = name
    } else if (result?.item) openedItem.value = result.item
    else unknownName.value = name
  }

  return { openedItem, unknownName, loadError, failedName, open }
}
