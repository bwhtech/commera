<script setup>
/**
 * Which installed apps could not act on this order. Nothing renders while every app took it, which is
 * the usual case, so the notice only costs space when there is something to do about it.
 */
import { computed, ref } from 'vue'
import { Alert, toast } from 'frappe-ui'
import { useMethodAction } from '../data/api'

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

const retryAction = useMethodAction('commera.app_events.retry_delivery')
const retryingApp = ref(null)

// Oldest first, so the app hears about the order in the order things happened to it.
async function retry(failure) {
  retryingApp.value = failure.app
  try {
    const rows = [...failure.rows].sort((left, right) => String(left.creation).localeCompare(String(right.creation)))
    for (const row of rows) {
      await retryAction.submit({ delivery: row.delivery })
      if (retryAction.error) return
    }
    toast.success(`Sending to ${failure.app} again`)
    emit('retried')
  } finally {
    retryingApp.value = null
  }
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
