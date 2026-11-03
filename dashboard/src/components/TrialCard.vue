<script setup>
import { SidebarCard } from 'frappe-ui'
import { loadBillingOnce, trialNotice } from '../data/cloudBilling'
import { openSettings } from '../ia/settings'
import { dismissTrialCard, isTrialCardShown } from '../ia/trialCard'

const emit = defineEmits(['open'])

loadBillingOnce()

function openBilling() {
  emit('open')
  openSettings('billing', { billingSurface: 'trial_card' })
}
</script>

<template>
  <SidebarCard
    v-if="isTrialCardShown"
    :theme="trialNotice.theme"
    :title="trialNotice.title"
    :description="trialNotice.description"
    :dismissible="trialNotice.dismissible"
    :action="{ label: trialNotice.actionLabel, onClick: openBilling }"
    @dismiss="dismissTrialCard"
  />
</template>
