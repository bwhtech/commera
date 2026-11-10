import { ref } from 'vue'
import { dayjs, toast } from 'frappe-ui'
import { useMethodAction } from './api'
import { errorMessage } from './errors'
import { __ } from './translation'
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
    return __('Next try {0}', [dayjs(row.next_retry_at).fromNow()])
  }
  return __('Waiting to send')
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
      if (!result.failed.length) toast.success(__('Sending to {0} again', [app]))
      else toast.error(bulkSummary(result, retrySentences(app), (error) => errorMessage(error)))
      onRetried()
    } finally {
      retrying.value = null
    }
  }

  return { retrying, retry }
}

function retrySentences(app) {
  return {
    all: (count) => (count === 1 ? __('1 delivery queued for {0}', [app]) : __('{0} deliveries queued for {1}', [count, app])),
    some: (done, total, failed) => __('{0} of {1} deliveries queued for {2}. {3} failed', [done, total, app, failed]),
  }
}
