import { ref } from 'vue'
import { dayjs, toast } from 'frappe-ui'
import { useMethodAction } from './api'
import { errorMessage } from './errors'
import { bulkSummary, runEach } from '../utils/runEach'

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

// Every delivery is retried even when one is refused, and the list is re-read either way: the
// ones before a refusal were already queued, and stopping there left the screen showing them failed.
export function useDeliveryRetry(onRetried) {
  const retryAction = useMethodAction('commera.plugin_events.retry_delivery', { quiet: true })
  const retrying = ref(null)

  async function retry(key, app, deliveries) {
    if (retrying.value) return
    retrying.value = key
    try {
      const result = await runEach(deliveries, (delivery) => retryAction.submit({ delivery }))
      if (!result.failed.length) toast.success(`Sending to ${app} again`)
      else toast.error(bulkSummary(result, ['delivery', 'deliveries'], `queued for ${app}`, (error) => errorMessage(error)))
      onRetried()
    } finally {
      retrying.value = null
    }
  }

  return { retrying, retry }
}
