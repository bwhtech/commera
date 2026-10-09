<script>
export const plugin = { label: '$label' }
</script>

<script setup>
import { computed } from 'vue'
import { EmptyState, useMethodRead, usePage } from '@commera/admin'

const summaryRequest = useMethodRead('$app_name.api.get_summary')
const ordersToday = computed(() => summaryRequest.data?.orders_today ?? 0)

usePage().setActions([
  {
    label: 'Refresh',
    icon: 'refresh-cw',
    loading: () => summaryRequest.loading,
    onClick: () => summaryRequest.reload(),
  },
])
</script>

<template>
  <template v-if="summaryRequest.data">
    <EmptyState
      v-if="!ordersToday"
      icon="lucide-$icon"
      title="Your awesome plugin"
      description="Edit commera/pages/$page_name/index.vue. With yarn dev running in apps/commera/dashboard, this page updates each time you save."
    />
    <div v-else>
      <p class="text-sm text-ink-gray-5">Store orders today</p>
      <p class="mt-1 text-2xl-semibold text-ink-gray-9 tabular-nums">{{ ordersToday }}</p>
    </div>
  </template>
</template>
