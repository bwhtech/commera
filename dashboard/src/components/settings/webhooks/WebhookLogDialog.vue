<script setup>
import { computed, watch } from 'vue'
import { Badge, Button, Dialog, Skeleton, dayjs, toast } from 'frappe-ui'
import { useAdminRead } from '../../../data/api'
import { __ } from '../../../data/translation'
import { LOG_STATUS_THEMES, eventLabel } from '../../../data/webhooks'

const props = defineProps({
  logName: { type: String, default: null },
})

const open = defineModel('open', { type: Boolean, default: false })
const emit = defineEmits(['replay'])

const logRequest = useAdminRead('webhooks.get_webhook_log', {
  params: () => ({ name: props.logName }),
  immediate: false,
})

// A row from the previous opening must not flash under the new one's title.
const log = computed(() => (logRequest.data?.name === props.logName ? logRequest.data : null))

watch(
  () => open.value && props.logName,
  (logName) => logName && logRequest.reload(),
  { immediate: true },
)

const body = computed(() => {
  if (!log.value?.body) return ''
  try {
    return JSON.stringify(JSON.parse(log.value.body), null, 2)
  } catch {
    return log.value.body
  }
})

async function copyBody() {
  await navigator.clipboard.writeText(body.value)
  toast.success(__('Body copied'))
}
</script>

<template>
  <Dialog v-model:open="open" size="2xl" :title="log ? eventLabel(log.event) : __('Log')">
    <template #default>
      <div v-if="!log" class="space-y-3" aria-hidden="true">
        <Skeleton v-for="row in 3" :key="row" class="h-10 w-full rounded-4" />
      </div>

      <div v-else class="space-y-5">
        <dl class="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
          <div>
            <dt class="text-xs text-ink-gray-5">{{ __('Status') }}</dt>
            <dd class="mt-1">
              <Badge variant="subtle" :theme="LOG_STATUS_THEMES[log.status] ?? 'gray'" :label="__(log.status)" />
            </dd>
          </div>
          <div>
            <dt class="text-xs text-ink-gray-5">{{ __('Response code') }}</dt>
            <dd class="mt-1 text-base text-ink-gray-8 tabular-nums">{{ log.response_code ?? __('None') }}</dd>
          </div>
          <div>
            <dt class="text-xs text-ink-gray-5">{{ __('Attempts') }}</dt>
            <dd class="mt-1 text-base text-ink-gray-8 tabular-nums">{{ log.attempts }}</dd>
          </div>
          <div>
            <dt class="text-xs text-ink-gray-5">{{ __('Sent') }}</dt>
            <dd class="mt-1 text-base text-ink-gray-8" :title="dayjs(log.creation).format('LLL')">
              {{ dayjs(log.creation).fromNow() }}
            </dd>
          </div>
        </dl>

        <div
          v-if="log.error && log.status !== 'Done'"
          class="rounded-4 border border-outline-red-2 bg-surface-red-1 px-3 py-2.5 text-p-sm text-ink-red-6"
        >
          <span class="font-medium">{{ log.error }}.</span>
          <template v-if="log.next_retry_at"> {{ __('Commera tries again {0}.', [dayjs(log.next_retry_at).fromNow()]) }}</template>
          <template v-else> {{ __('Commera has stopped retrying this event.') }}</template>
        </div>

        <div v-if="log.headers?.length">
          <h4 class="text-sm text-ink-gray-5">{{ __('Headers') }}</h4>
          <dl class="mt-1.5 divide-y divide-outline-gray-1 rounded-4 border border-outline-gray-1">
            <div v-for="[name, value] in log.headers" :key="name" class="flex gap-4 px-3 py-2 font-mono text-xs">
              <dt class="w-44 shrink-0 text-ink-gray-5">{{ name }}</dt>
              <dd class="min-w-0 truncate text-ink-gray-8" :title="value">{{ value }}</dd>
            </div>
          </dl>
        </div>

        <div>
          <div class="flex items-center justify-between">
            <h4 class="text-sm text-ink-gray-5">{{ __('Body') }}</h4>
            <Button size="sm" variant="ghost" icon-left="lucide-copy" :label="__('Copy')" @click="copyBody" />
          </div>
          <pre class="mt-1.5 max-h-64 overflow-auto rounded-4 bg-surface-gray-1 p-3 font-mono text-xs text-ink-gray-8">{{ body }}</pre>
        </div>
      </div>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Close')" @click="open = false" />
        <Button
          variant="solid"
          theme="gray"
          icon-left="lucide-rotate-ccw"
          :label="__('Replay')"
          :disabled="!log"
          @click="emit('replay', log)"
        />
      </div>
    </template>
  </Dialog>
</template>
