<script setup>
import { computed, ref, watch } from 'vue'
import { Badge, Button, Skeleton, dayjs, dialog, toast } from 'frappe-ui'
import EmptyState from '../../EmptyState.vue'
import ListPagination from '../../ListPagination.vue'
import WebhookLogDialog from './WebhookLogDialog.vue'
import { useAdminRead } from '../../../data/api'
import { LOG_STATUS_THEMES, eventLabel, webhookActions } from '../../../data/webhooks'

const props = defineProps({
  name: { type: String, required: true },
  host: { type: String, required: true },
  active: { type: Boolean, default: false },
})

const emit = defineEmits(['send-test', 'replayed'])

const page = ref(1)
const pageSize = ref(20)

const logsRequest = useAdminRead('webhooks.get_webhook_logs', {
  params: () => ({ webhook: props.name, start: (page.value - 1) * pageSize.value, page_length: pageSize.value }),
  immediate: false,
})
const logs = computed(() => logsRequest.data?.rows ?? [])

watch(
  () => props.active,
  (isActive) => isActive && !logsRequest.data && !logsRequest.loading && logsRequest.reload(),
  { immediate: true },
)
watch([page, pageSize], () => logsRequest.reload())

const STATUS_DOTS = { Done: 'bg-surface-green-7', Retrying: 'bg-surface-amber-7', Failed: 'bg-surface-red-7' }

const openLogName = ref(null)
const isLogOpen = ref(false)

function inspect(log) {
  openLogName.value = log.name
  isLogOpen.value = true
}

// Back to the first page, where a new row lands; changing the page reloads by itself.
async function reload() {
  if (page.value !== 1) page.value = 1
  else await logsRequest.reload()
}

function replay(log) {
  dialog.confirm({
    title: `Replay ${eventLabel(log.event).toLowerCase()}?`,
    message: `Commera sends this event to ${props.host} again, with the same body and event id. A receiver that skips event ids it has already handled will ignore it.`,
    confirmLabel: 'Replay',
    onConfirm: async () => {
      const replayed = await webhookActions.call('replay', { log: log.name })
      if (!replayed) return
      isLogOpen.value = false
      await reload()
      emit('replayed')
      if (replayed.status === 'Failed') toast.error(`Replay to ${props.host} failed: ${replayed.error ?? 'no answer'}`)
      else toast.success(`Replayed to ${props.host}`)
    },
  })
}

defineExpose({ reload })
</script>

<template>
  <div v-if="logsRequest.loading && !logsRequest.data" class="space-y-3" aria-hidden="true">
    <Skeleton v-for="row in 3" :key="row" class="h-10 w-full rounded-4" />
  </div>

  <EmptyState
    v-else-if="!logs.length"
    compact
    icon="lucide-send"
    title="Nothing sent yet"
    description="Logs show here when a subscribed event is sent. Send a test event to check the endpoint now."
  >
    <Button class="mt-2" icon-left="lucide-send" label="Send test event" @click="emit('send-test')" />
  </EmptyState>

  <template v-else>
    <ul class="divide-y divide-outline-gray-1 border-y border-outline-gray-1">
      <li v-for="log in logs" :key="log.name" class="group flex items-center gap-1 rounded-4 pr-1 hover:bg-surface-gray-1">
        <button
          type="button"
          class="flex min-w-0 flex-1 items-center gap-3 rounded-4 px-2 py-2.5 text-left"
          @click="inspect(log)"
        >
          <span class="size-2 shrink-0 rounded-full" :class="STATUS_DOTS[log.status]" aria-hidden="true" />
          <span class="min-w-0 flex-1">
            <span class="flex min-w-0 items-center gap-1.5 text-base text-ink-gray-8">
              <span class="truncate">
                {{ eventLabel(log.event) }}
                <span v-if="log.reference_name" class="text-ink-gray-5">· {{ log.reference_name }}</span>
              </span>
              <Badge v-if="log.replay_of" class="shrink-0" variant="outline" theme="gray" size="sm" label="Replay" />
            </span>
            <span class="block truncate font-mono text-2xs text-ink-gray-4">{{ log.event_id }}</span>
          </span>
          <span class="w-20 shrink-0 text-right">
            <Badge variant="subtle" :theme="LOG_STATUS_THEMES[log.status] ?? 'gray'" :label="log.status" />
          </span>
          <span class="w-24 shrink-0 text-right text-sm text-ink-gray-5" :title="dayjs(log.creation).format('LLL')">
            {{ dayjs(log.creation).fromNow() }}
          </span>
        </button>
        <Button
          size="sm"
          variant="ghost"
          icon-left="lucide-rotate-ccw"
          label="Replay"
          class="shrink-0 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100"
          @click="replay(log)"
        />
      </li>
    </ul>
    <ListPagination v-model:page="page" v-model:page-size="pageSize" :total="logsRequest.data.total" />
  </template>

  <WebhookLogDialog v-model:open="isLogOpen" :log-name="openLogName" @replay="replay" />
</template>
