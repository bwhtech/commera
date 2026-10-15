import { ref } from 'vue'
import { dayjs, toast } from 'frappe-ui'
import { useMethodAction } from './api'

export function eventLabel(event) {
  const words = event.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export function statusKey(row) {
  if (row.status === 'Done') return 'sent'
  if (row.status === 'Failed') return 'failed'
  if (row.status === 'Running') return 'sending'
  return row.attempts > 0 ? 'retrying' : 'queued'
}

export function timeLabel(row) {
  if (row.status !== 'Queued') return dayjs(row.finished_at || row.creation).fromNow()
  // A due retry sits queued until the next worker or scheduler sweep picks it up.
  if (row.next_retry_at && dayjs(row.next_retry_at).isAfter(dayjs())) {
    return `Next try ${dayjs(row.next_retry_at).fromNow()}`
  }
  return 'Waiting to send'
}

export function useDeliveryRetry(onRetried) {
  const retryAction = useMethodAction('commera.plugin_events.retry_delivery')
  const retrying = ref(null)

  async function retry(key, app, deliveries) {
    retrying.value = key
    try {
      for (const delivery of deliveries) {
        await retryAction.submit({ delivery })
        if (retryAction.error) return
      }
      toast.success(`Sending to ${app} again`)
      onRetried()
    } finally {
      retrying.value = null
    }
  }

  return { retrying, retry }
}
