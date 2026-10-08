<script setup>
import { Button, SettingsBody, SettingsRow } from 'frappe-ui'
import SettingsPanelHeader from './SettingsPanelHeader.vue'
import EmptyState from '../EmptyState.vue'
import SettingsLinkControl from './SettingsLinkControl.vue'
import SettingsSkeleton from './SettingsSkeleton.vue'
import { useSettingsTab } from '../../data/useSettingsTab'

const props = defineProps({
  // Opening the Emails tab should fetch; switching away and back should not.
  active: { type: Boolean, default: false },
})

const TEMPLATE_FIELD = { options: 'Email Template' }

const TEMPLATE_ROWS = [
  {
    fieldname: 'order_confirmation_email_template',
    title: 'Order confirmation',
    description: 'Sent when a customer places an order.',
  },
  {
    fieldname: 'order_cancellation_email_template',
    title: 'Order cancellation',
    description: 'Sent when an order is cancelled.',
  },
  {
    fieldname: 'item_in_stock_email_template',
    title: 'Back in stock',
    description: 'Sent to customers waiting on a product when it is restocked.',
  },
]

const { settings, values, commit } = useSettingsTab('emails', () => props.active)
</script>

<template>
  <SettingsPanelHeader
    title="Templates"
    description="The template each store email is sent with."
  />

  <SettingsBody v-scroll-fade>
    <EmptyState
      v-if="settings.error"
      compact
      icon="lucide-triangle-alert"
      title="This could not be loaded"
      description="Your emails still go out. This panel just cannot say which templates they use."
    >
      <Button label="Try again" variant="subtle" theme="gray" @click="settings.reload()" />
    </EmptyState>

    <SettingsSkeleton v-else-if="settings.loading && !settings.data" :rows="3" />

    <div v-else class="divide-y divide-outline-gray-1">
      <SettingsRow
        v-for="row in TEMPLATE_ROWS"
        :key="row.fieldname"
        :title="row.title"
        :description="row.description"
      >
        <SettingsLinkControl
          :field="TEMPLATE_FIELD"
          :model-value="values[row.fieldname] ?? ''"
          options-path="settings.get_link_options"
          required
          @update:model-value="commit(row.fieldname, $event, row.title)"
        />
      </SettingsRow>
    </div>
  </SettingsBody>
</template>
