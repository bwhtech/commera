<script>
export const plugin = { label: '$label' }
</script>

<script setup>
import { usePlugin } from '@commera/admin'

const { record } = usePlugin()
</script>

<template>
  <p class="text-p-sm text-ink-gray-6">Build this card for {{ record.name }} in commera/$folder/index.vue.</p>
</template>
