<script setup>
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import { healthOf } from '../../../data/webhooks'

const props = defineProps({
  webhook: { type: Object, required: true },
})

const health = computed(() => healthOf(props.webhook))
</script>

<template>
  <Badge variant="subtle" :theme="health.theme" :label="health.label" />
</template>
