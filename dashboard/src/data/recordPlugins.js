import { computed, ref, shallowRef, watch } from 'vue'
import { dialog, toast } from 'frappe-ui'
import { useAdminAction, useAdminRead } from './api'
import { pluginIcon, placeEntries } from '../ia/plugins'

export function usePluginRun(path, paramsOf, { onDone } = {}) {
  const runAction = useAdminAction(path)

  async function run(entry) {
    const result = await runAction.submit(paramsOf(entry))
    if (runAction.error) return
    toast.success(result?.message || `${entry.label} done`)
    onDone?.()
  }

  return function confirmAndRun(entry) {
    if (!entry.confirm) return run(entry)
    dialog.confirm({ title: entry.label, message: entry.confirm, confirmLabel: entry.label, onConfirm: () => run(entry) })
  }
}

// Conditional entries stay hidden until their one request per record answers, so nothing flashes in and back out.
export function useRecordPlugins(place, doctype, nameGetter, { onReload } = {}) {
  const cardEntries = placeEntries(`${place}/cards`)
  const actionEntries = placeEntries(`${place}/actions`)
  const hasConditions = [...cardEntries, ...actionEntries].some((entry) => entry.has_condition)

  const conditionsRequest = useAdminRead('plugins.get_record_plugins', { immediate: false })
  const resolved = shallowRef({ name: null, keys: new Set() })

  // Moving to the next order mid-request answers for the old one, so an answer only counts for its own record.
  async function resolveConditions() {
    const name = nameGetter()
    if (!hasConditions || !name) return
    const result = await conditionsRequest.submit({ doctype, name })
    if (conditionsRequest.error || nameGetter() !== name) return
    resolved.value = { name, keys: new Set(result?.keys ?? []) }
  }

  watch(nameGetter, resolveConditions, { immediate: true })

  function isVisible(entry) {
    if (!entry.has_condition) return true
    return resolved.value.name === nameGetter() && resolved.value.keys.has(entry.key)
  }

  const cards = computed(() => cardEntries.filter(isVisible))
  const actions = computed(() => actionEntries.filter(isVisible))
  // Bumped on every reload so the cards remount and fetch again after an action changed the record.
  const revision = ref(0)
  const record = computed(() => ({ doctype, name: nameGetter(), revision: revision.value }))

  // The action whose dialog is open. The menu that opened it has already closed, so no dialog stacks on another.
  const openAction = shallowRef(null)

  function reload() {
    revision.value += 1
    onReload?.()
    resolveConditions()
  }

  const runEntry = usePluginRun('plugins.run_record_action', (entry) => ({ key: entry.key, name: nameGetter() }), {
    onDone: reload,
  })

  function start(entry) {
    if (!entry.has_method) {
      openAction.value = entry
      return
    }
    return runEntry(entry)
  }

  const actionGroup = computed(() =>
    actions.value.length
      ? {
          group: 'Plugins',
          options: actions.value.map((entry) => ({
            label: entry.label,
            icon: pluginIcon(entry),
            onClick: () => start(entry),
          })),
        }
      : null,
  )

  return { cards, actionGroup, openAction, record, reload }
}
