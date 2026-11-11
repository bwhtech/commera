<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Alert, Button, Dropdown, FormControl, SettingsBody, Switch, TabButtons, dayjs, dialog, toast } from 'frappe-ui'
import EmptyState from '../../EmptyState.vue'
import SettingsPanelHeader from '../SettingsPanelHeader.vue'
import SettingsSkeleton from '../SettingsSkeleton.vue'
import WebhookEventPicker from './WebhookEventPicker.vue'
import WebhookHealthBadge from './WebhookHealthBadge.vue'
import WebhookLogs from './WebhookLogs.vue'
import WebhookSecret from './WebhookSecret.vue'
import { useAdminAction, useAdminRead } from '../../../data/api'
import { __ } from '../../../data/translation'
import { useSettingsAutosave } from '../../../data/useSettingsAutosave'
import { hostOf, webhookActions, webhookStore } from '../../../data/webhooks'

const props = defineProps({
  name: { type: String, required: true },
  // Handed over once by the add dialog: the server never shows a new secret again unasked.
  createdSecret: { type: String, default: null },
})

const emit = defineEmits(['back'])

const TABS = [
  { label: __('Events'), value: 'events' },
  { label: __('Logs'), value: 'logs' },
]

const webhookRequest = useAdminRead('webhooks.get_webhook', { params: () => ({ name: props.name }) })
const webhook = ref(null)

const updateAction = useAdminAction('webhooks.update_webhook')
const { values, stored, adopt, set, commit } = useSettingsAutosave(updateAction, { params: { name: props.name } })

function applyWebhook(record) {
  webhook.value = record
  webhookStore.reload()
}

watch(
  () => webhookRequest.data,
  (record) => {
    if (!record) return
    // Only the first answer fills the boxes: a later re-read (after a test, a retry) must not
    // overwrite a URL being typed or a tick still waiting to save.
    if (!webhook.value) adopt({ url: record.url, events: record.events })
    webhook.value = record
  },
  { immediate: true },
)

const listed = computed(() => webhookStore.webhooks.value.find((row) => row.name === props.name))
const host = computed(() => hostOf(webhook.value?.url ?? listed.value?.url ?? ''))

const tab = ref('events')
const logsPanel = ref(null)
const secret = ref(props.createdSecret)
const isSecretShown = ref(Boolean(props.createdSecret))
const isJustCreated = ref(Boolean(props.createdSecret))

const isAutoDisabled = computed(() => Boolean(webhook.value?.auto_disabled_at) && !webhook.value.enabled)
const isFailing = computed(() => Boolean(webhook.value?.enabled) && webhook.value.failing_count > 0)

const failingTitle = computed(() => {
  const count = webhook.value.failing_count
  return count === 1 ? __('1 event has not arrived') : __('{0} events have not arrived', [count])
})

const lastError = computed(() => webhook.value?.last_error ?? __('with an error'))

async function setEnabled(isOn) {
  const record = await webhookActions.call('update_webhook', { name: props.name, enabled: isOn ? 1 : 0 })
  if (!record) return
  applyWebhook(record)
  toast.success(isOn ? __('Webhook turned on') : __('Webhook turned off'))
}

function saveUrl(url) {
  commit('url', url.trim(), __('Endpoint URL'), (record) => {
    adopt({ url: record.url })
    applyWebhook(record)
  })
}

// A few ticks of a checkbox become one save; only the server's answer moves `stored`, so a later
// click is never overwritten by an earlier answer.
let eventsTimer = null
function setEvents(events) {
  set('events', events)
  clearTimeout(eventsTimer)
  eventsTimer = setTimeout(saveEvents, 400)
}

function saveEvents() {
  eventsTimer = null
  if (!values.value.events.length) {
    toast.error(__('Choose at least one event.'))
    values.value.events = stored.value.events
    return
  }
  commit('events', values.value.events, __('Events'), (record) => {
    stored.value = { ...stored.value, events: record.events }
    applyWebhook(record)
  })
}

// Flushed, not dropped: Back within the debounce would otherwise lose the last tick without a word.
// The commit outlives this component, so its answer still lands in the shared webhook store.
onBeforeUnmount(() => {
  if (!eventsTimer) return
  clearTimeout(eventsTimer)
  eventsTimer = null
  saveEvents()
})

async function retryFailed() {
  const answer = await webhookActions.call('retry_failed', { webhook: props.name })
  if (!answer) return
  toast.success(
    answer.count === 1 ? __('1 event queued to retry') : __('{0} events queued to retry', [answer.count]),
  )
  webhookRequest.reload()
  logsPanel.value?.reload()
}

const sendingTest = ref(false)

async function sendTest() {
  if (sendingTest.value) return
  sendingTest.value = true
  const log = await webhookActions.call('send_test', { name: props.name })
  sendingTest.value = false
  if (!log) return
  tab.value = 'logs'
  await nextTick()
  logsPanel.value?.reload()
  webhookRequest.reload()
  webhookStore.reload()
  const reason = log.error ?? log.response_code ?? __('no answer')
  if (log.status === 'Done') toast.success(__('Test event sent: {0}', [log.response_code]))
  else if (log.status === 'Retrying') toast.warning(__('Test event failed: {0}. It will retry.', [reason]))
  else toast.error(__('Test event failed: {0}', [reason]))
}

function rotateSecret() {
  dialog.confirm({
    title: __('Rotate the signing secret?'),
    message: __(
      'Requests are signed with the new secret straight away. Update the receiving app first, or it will reject every event until you do.',
    ),
    confirmLabel: __('Rotate secret'),
    onConfirm: async () => {
      const answer = await webhookActions.call('rotate_secret', { name: props.name })
      if (!answer) return
      secret.value = answer.secret
      isSecretShown.value = true
      webhookRequest.reload()
      toast.success(__('Secret rotated'))
    },
  })
}

function deleteWebhook() {
  dialog.danger({
    title: __('Delete the webhook to {0}?', [host.value]),
    message: __('Commera stops sending events to this URL. Events that are waiting to retry are dropped.'),
    confirmLabel: __('Delete webhook'),
    onConfirm: async () => {
      const { error } = await webhookActions.attempt('delete_webhook', { name: props.name })
      if (error) return
      webhookStore.reload()
      emit('back')
      toast.success(__('Webhook deleted'))
    },
  })
}

const menu = [
  { label: __('Send test event'), icon: 'lucide-send', onClick: sendTest },
  { label: __('Rotate secret'), icon: 'lucide-key-round', onClick: rotateSecret },
  { label: __('Delete webhook'), icon: 'lucide-trash-2', theme: 'red', onClick: deleteWebhook },
]
</script>

<template>
  <!-- The default slot, not #actions: frappe-ui's header drops #actions once a default slot is given. -->
  <SettingsPanelHeader>
    <div class="flex min-w-0 flex-wrap items-center gap-2">
      <Button variant="ghost" icon="lucide-arrow-left rtl:-scale-x-100" :label="__('Back to webhooks')" @click="emit('back')" />
      <h2 class="min-w-0 truncate text-lg font-semibold text-ink-gray-8">{{ host }}</h2>
      <WebhookHealthBadge v-if="webhook" :webhook="webhook" />
      <div v-if="webhook" class="ms-auto flex shrink-0 items-center gap-2">
        <Button icon-left="lucide-send" :label="__('Send test')" :loading="sendingTest" @click="sendTest" />
        <Dropdown :options="menu" align="end">
          <Button icon="lucide-ellipsis" :label="__('More actions')" />
        </Dropdown>
      </div>
    </div>
  </SettingsPanelHeader>

  <SettingsBody v-scroll-fade>
    <EmptyState
      v-if="webhookRequest.error && !webhook"
      compact
      icon="lucide-webhook"
      :title="__('This webhook could not be opened')"
      :description="__('It may have been deleted.')"
    >
      <Button class="mt-2" :label="__('Back to webhooks')" @click="emit('back')" />
    </EmptyState>

    <SettingsSkeleton v-else-if="!webhook" class="mt-2" :rows="4" />

    <template v-else>
      <Alert
        v-if="isJustCreated"
        class="mb-4 !bg-surface-gray-2"
        theme="blue"
        :title="__('Copy the signing secret into the receiving app')"
        :description="__('It checks the X-Commera-Hmac-Sha256 header with this secret before it trusts an event.')"
        dismissible
        @dismiss="isJustCreated = false"
      />
      <Alert
        v-if="isAutoDisabled"
        class="mb-4 !bg-surface-gray-2"
        theme="red"
        :title="__('Commera turned this webhook off')"
        :description="
          __(
            '{0} attempts failed within 24 hours. The endpoint last answered {1}. Events since {2} were not sent. Fix the endpoint, then turn the webhook back on.',
            [webhook.failure_limit, lastError, dayjs(webhook.auto_disabled_at).format('D MMM, h:mm A')],
          )
        "
        :primary-action="{ label: __('Turn back on'), variant: 'solid', theme: 'gray', onClick: () => setEnabled(true) }"
      />
      <Alert
        v-else-if="isFailing"
        class="mb-4 !bg-surface-gray-2"
        theme="amber"
        :title="failingTitle"
        :description="
          __(
            'The endpoint answered {0}. {1} of {2} attempts failed in the last 24 hours. After {2} failed attempts it will automatically be turned off.',
            [lastError, webhook.failed_attempts, webhook.failure_limit],
          )
        "
        :primary-action="{ label: __('Retry now'), variant: 'solid', theme: 'gray', onClick: retryFailed }"
      />

      <div class="space-y-4">
        <div class="flex items-center justify-between gap-4 rounded-4 border border-outline-gray-1 px-3 py-2.5">
          <div class="min-w-0">
            <p class="text-base text-ink-gray-8">{{ __('Send events') }}</p>
            <p class="text-p-sm text-ink-gray-5">
              {{
                __(
                  'While off, Commera does not record or send events for this webhook. It turns a webhook off itself after {0} failed attempts within 24 hours.',
                  [webhook.failure_limit],
                )
              }}
            </p>
          </div>
          <Switch :model-value="Boolean(webhook.enabled)" :aria-label="__('Send events')" @update:model-value="setEnabled" />
        </div>

        <FormControl
          type="url"
          :label="__('Endpoint URL')"
          :model-value="values.url"
          @update:model-value="(url) => set('url', url)"
          @change="saveUrl($event.target.value)"
        />

        <WebhookSecret v-model:secret="secret" v-model:shown="isSecretShown" :name="name" :hint="webhook.secret_hint" />
      </div>

      <TabButtons v-model="tab" class="mt-8" :options="TABS" :aria-label="__('Webhook sections')" />

      <div v-if="tab === 'events'" class="mt-4">
        <WebhookEventPicker :model-value="values.events ?? []" @update:model-value="setEvents" />
      </div>
      <div v-show="tab === 'logs'" class="mt-3">
        <WebhookLogs
          ref="logsPanel"
          :name="name"
          :host="host"
          :active="tab === 'logs'"
          @send-test="sendTest"
          @replayed="webhookRequest.reload()"
        />
      </div>
    </template>
  </SettingsBody>
</template>
