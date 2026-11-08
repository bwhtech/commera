import { computed, onScopeDispose, ref, shallowRef, watch } from 'vue'
import { dialog, toast } from 'frappe-ui'
import { useAdminAction, useAdminRead, trySubmit } from './api'
import { pluginIcon, placeEntries } from '../ia/plugins'
import { createSequence } from '../utils/sequence'

export function usePluginRun(path, paramsOf, { onDone } = {}) {
  const runAction = useAdminAction(path)

  async function run(entry) {
    const ran = await trySubmit(runAction, paramsOf(entry))
    if (!ran) return
    const result = runAction.data
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

  // Quiet: it is a background check the merchant did not ask for, and it retries on its own.
  const conditionsRequest = useAdminRead('plugins.get_record_plugins', { immediate: false, quiet: true })
  const resolved = shallowRef({ name: null, keys: new Set() })

  // A failed check used to leave the record's conditional entries hidden until something reloaded
  // it. It is retried a couple of times, slower each time, for as long as the record stays open.
  const RETRY_DELAYS_MS = [2000, 8000]
  const checks = createSequence()
  let retryTimer = null

  // Moving to the next order mid-request answers for the old one, so an answer only counts for its
  // own record, and only the newest check may answer at all.
  async function resolveConditions(attempt = 0) {
    clearTimeout(retryTimer)
    const name = nameGetter()
    if (!hasConditions || !name) return
    const ticket = checks.next()
    const answered = await trySubmit(conditionsRequest, { doctype, name })
    if (!checks.isLatest(ticket) || nameGetter() !== name) return
    if (!answered) {
      if (attempt < RETRY_DELAYS_MS.length) {
        retryTimer = setTimeout(() => resolveConditions(attempt + 1), RETRY_DELAYS_MS[attempt])
      }
      return
    }
    const result = conditionsRequest.data
    resolved.value = { name, keys: new Set(result?.keys ?? []) }
  }

  onScopeDispose(() => {
    clearTimeout(retryTimer)
    checks.cancel()
  })

  watch(nameGetter, () => resolveConditions(), { immediate: true })

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
