<script setup>
import { Button } from 'frappe-ui'
import SettingsPanelHeader from './SettingsPanelHeader.vue'

defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
})

const emit = defineEmits(['back'])
</script>

<template>
  <SettingsPanelHeader :title="title" :description="description">
    <template #actions>
      <Button :label="__('Back')" icon-left="lucide-arrow-left rtl:-scale-x-100" @click="emit('back')" />
      <!-- Saving differs per screen: one emits, one submits a form. -->
      <slot name="actions" />
    </template>
  </SettingsPanelHeader>
</template>
