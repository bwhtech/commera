import { computed, ref, watch } from 'vue'

export function changePending(pending, key, field, value, submitted = {}) {
  // A successful save will replace the displayed value with the submitted one.
  const inFlight = Object.hasOwn(submitted, key)
  const baseline = inFlight ? submitted[key] : field.value
  if (value === baseline && (inFlight || field.status !== 'outdated')) delete pending[key]
  else pending[key] = value
}

export async function savePending(pending, submit) {
  const submitted = { ...pending }
  let saved = null
  try {
    saved = await submit(submitted)
    return saved
  } finally {
    for (const [key, value] of Object.entries(submitted)) {
      if (saved !== null && pending[key] === value) delete pending[key]
      else if (saved === null && !Object.hasOwn(pending, key)) pending[key] = value
    }
  }
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
