<script setup>
import { computed } from 'vue'
import { Alert } from 'frappe-ui'
import { useDeliveryRetry } from '../data/pluginEvents'

const props = defineProps({
  failures: { type: Array, default: () => [] },
})

const emit = defineEmits(['retried'])

// The rows carry the app's title, not its module name, so they group by what the owner reads.
const failuresByApp = computed(() => {
  const groups = new Map()
  for (const row of props.failures) groups.set(row.app, [...(groups.get(row.app) ?? []), row])
  return [...groups.entries()].map(([app, rows]) => ({ app, rows }))
})

const { retrying: retryingApp, retry: retryDeliveries } = useDeliveryRetry(() => emit('retried'))

// Oldest first, so the app hears about the order in the order things happened to it.
function retry(failure) {
  const rows = [...failure.rows].sort((left, right) => String(left.creation).localeCompare(String(right.creation)))
  return retryDeliveries(failure.app, failure.app, rows.map((row) => row.delivery))
}

function retryAlertAction(failure) {
  if (!failure.rows.some((row) => row.can_retry)) return undefined
  return {
    label: 'Retry',
    iconLeft: 'lucide-rotate-cw',
    loading: retryingApp.value === failure.app,
    disabled: Boolean(retryingApp.value),
    onClick: () => retry(failure),
  }
}

function description(failure) {
  const count = failure.rows.length
  return count === 1 ? 'One update did not reach it.' : `${count} updates did not reach it.`
}
</script>

<template>
  <div v-if="failuresByApp.length" class="space-y-2">
    <Alert
      v-for="failure in failuresByApp"
      :key="failure.app"
      theme="red"
      :title="`${failure.app} couldn't process this order`"
      :description="description(failure)"
      :primary-action="retryAlertAction(failure)"
    />
  </div>
</template>
