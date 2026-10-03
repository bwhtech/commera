<script setup>
/**
 * What the installed apps were told about this order. Rendered twice like
 * OrderCustomerPanel, so the parent owns the read and this only retries.
 */
import { ref } from 'vue'
import { Button, Skeleton, dayjs, toast } from 'frappe-ui'
import StatusBadge from './StatusBadge.vue'
import { useMethodAction } from '../data/api'

defineProps({
  events: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['retried'])

const EVENT_LABELS = {
  order_placed: 'Order placed',
  order_paid: 'Order paid',
  order_cancelled: 'Order cancelled',
  order_fulfilled: 'Order fulfilled',
  order_delivered: 'Order delivered',
  order_refunded: 'Order refunded',
}

function eventLabel(event) {
  if (EVENT_LABELS[event]) return EVENT_LABELS[event]
  const words = event.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

function statusKey(row) {
  if (row.status === 'Done') return 'sent'
  if (row.status === 'Failed') return 'failed'
  if (row.status === 'Running') return 'sending'
  return row.attempts > 0 ? 'retrying' : 'queued'
}

function timeLabel(row) {
  if (row.status !== 'Queued') return dayjs(row.finished_at || row.creation).fromNow()
  // A due retry sits queued until the next worker or scheduler sweep picks it up.
  if (row.next_retry_at && dayjs(row.next_retry_at).isAfter(dayjs())) {
    return `Next try ${dayjs(row.next_retry_at).fromNow()}`
  }
  return 'Waiting to send'
}

const retryAction = useMethodAction('commera.app_events.retry_delivery')
const retryingDelivery = ref(null)

async function retry(row) {
  retryingDelivery.value = row.delivery
  try {
    await retryAction.submit({ delivery: row.delivery })
    if (retryAction.error) return
    toast.success(`Sending to ${row.app} again`)
    emit('retried')
  } finally {
    retryingDelivery.value = null
  }
}
</script>

<template>
  <section class="px-4 py-4">
    <p class="text-sm text-ink-gray-5">Apps</p>

    <div v-if="loading" class="mt-2 space-y-3">
      <div v-for="placeholder in 2" :key="placeholder" class="space-y-2">
        <div class="flex items-center justify-between gap-3">
          <Skeleton class="h-4 w-28 rounded-4" />
          <Skeleton class="h-5 w-12 rounded-4" />
        </div>
        <Skeleton class="h-3.5 w-36 rounded-4" />
      </div>
    </div>

    <ul v-else class="mt-2 space-y-3">
      <li v-for="row in events" :key="row.delivery">
        <div class="flex items-center justify-between gap-3">
          <p class="min-w-0 truncate text-base text-ink-gray-8">{{ eventLabel(row.event) }}</p>
          <StatusBadge class="shrink-0" :status="statusKey(row)" />
        </div>
        <p class="mt-1 flex min-w-0 gap-1 text-sm text-ink-gray-5">
          <span class="min-w-0 truncate">{{ row.app }}</span>
          <span class="shrink-0">· {{ timeLabel(row) }}</span>
        </p>
        <Button
          v-if="row.status === 'Failed' && row.can_retry"
          class="mt-2"
          size="sm"
          label="Retry"
          icon-left="lucide-rotate-cw"
          :loading="retryingDelivery === row.delivery"
          :disabled="Boolean(retryingDelivery)"
          @click="retry(row)"
        />
      </li>
    </ul>
  </section>
</template>
