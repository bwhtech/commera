import { computed, effectScope } from 'vue'
import { createAdminCaller } from './adminCaller'
import { useAdminRead } from './api'

// A module-level read, not one inside the panel: the settings sidebar shows a failing webhook's
// dot before the tab is ever opened.

export const TEST_EVENT = 'webhook_test'

// The scope is detached: these reads outlive whichever component first opened the panel.
const scope = effectScope(true)
const { listRequest, groupsRequest } = scope.run(() => ({
  listRequest: useAdminRead('webhooks.get_webhooks', { immediate: false }),
  groupsRequest: useAdminRead('webhooks.get_event_groups', { immediate: false }),
}))

const webhooks = computed(() => listRequest.data ?? [])
const eventGroups = computed(() => groupsRequest.data ?? [])
const hasFailingWebhook = computed(() => webhooks.value.some((webhook) => webhook.enabled && webhook.is_failing))

const eventLabels = computed(
  () => new Map(eventGroups.value.flatMap((group) => group.events.map((event) => [event.event, event.label]))),
)

function loadOnce() {
  if (!listRequest.isFinished && !listRequest.loading) listRequest.reload()
  if (!groupsRequest.isFinished && !groupsRequest.loading) groupsRequest.reload()
}

export const webhookStore = {
  listRequest,
  groupsRequest,
  webhooks,
  eventGroups,
  hasFailingWebhook,
  loadOnce,
  reload: () => listRequest.reload(),
}

export const webhookActions = createAdminCaller('webhooks.')

export function eventLabel(event) {
  if (event === TEST_EVENT) return 'Test event'
  return eventLabels.value.get(event) ?? event
}

function parseUrl(url) {
  try {
    return new URL(url)
  } catch {
    return null
  }
}

export function hostOf(url) {
  return parseUrl(url)?.host ?? url
}

export function pathOf(url) {
  const parsed = parseUrl(url)
  return parsed ? parsed.pathname + parsed.search : ''
}

const HEALTH = {
  off: { label: 'Off', theme: 'gray' },
  failing: { label: 'Failing', theme: 'amber' },
  new: { label: 'Nothing sent yet', theme: 'blue' },
  active: { label: 'Active', theme: 'green' },
}

export function healthOf(webhook) {
  if (!webhook.enabled) return HEALTH.off
  if (webhook.is_failing) return HEALTH.failing
  if (!webhook.last_sent_at) return HEALTH.new
  return HEALTH.active
}

export const LOG_STATUS_THEMES = { Done: 'green', Retrying: 'amber', Failed: 'red' }

export function plural(count, word) {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}
