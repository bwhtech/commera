<script setup>
import { TabButtons } from 'frappe-ui'
import { useIsMobile } from '../utils/useIsMobile'

defineProps({ options: { type: Array, required: true } })
const model = defineModel({ type: String, required: true })

const isMobile = useIsMobile()
</script>

<template>
  <!-- On a phone the tabs get their own row. `flex-auto` beats fluid's equal `flex-1` widths, which cut
       "Scheduled" short; $attrs land on TabButtons' outer element, so it needs the `w-full`. -->
  <TabButtons
    v-model="model"
    size="sm"
    :options="options"
    :fluid="isMobile"
    :class="{ 'w-full [&_[data-slot=tab-button]]:flex-auto': isMobile }"
  />
</template>
