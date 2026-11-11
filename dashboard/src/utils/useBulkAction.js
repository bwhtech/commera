import { ref } from 'vue'
import { toast } from 'frappe-ui'
import { errorMessage } from '../data/errors'
import { bulkSummary, runEach } from './runEach'

// One bulk action at a time per screen. `running` names the action in flight (null when none), so
// its button can spin and the rest of the bar stay shut; a second click while one runs is ignored
// rather than starting a loop that would abort the first one's shared request.
// `write(item)` should come from a `quiet` action: a hundred refusals would otherwise be a hundred
// toasts, and the run ends with one summary instead.
export function useBulkAction() {
  const running = ref(null)

  async function run(label, items, write, { sentences, after }) {
    if (running.value || !items.length) return null
    running.value = label
    try {
      const result = await runEach(items, write)
      const message = bulkSummary(result, sentences, (error) => errorMessage(error))
      if (result.failed.length) toast.error(message)
      else toast.success(message)
      // Reloaded whatever happened: the writes before a refusal landed.
      await after?.(result)
      return result
    } finally {
      running.value = null
    }
  }

  return { running, run }
}
