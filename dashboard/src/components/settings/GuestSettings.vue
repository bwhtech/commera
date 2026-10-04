<script setup>
import { computed, watch } from 'vue'
import { Button, SettingsBody, SettingsRow, Switch, TextInput } from 'frappe-ui'
import SettingsPanelHeader from './SettingsPanelHeader.vue'
import EmptyState from '../EmptyState.vue'
import SettingsSkeleton from './SettingsSkeleton.vue'
import { useAdminAction, useAdminRead } from '../../data/api'
import { useSettingsAutosave } from '../../data/useSettingsAutosave'

const props = defineProps({
  // Opening the Guest tab should fetch; switching away and back should not.
  active: { type: Boolean, default: false },
})

const settings = useAdminRead('settings.get_guest_settings', { immediate: false })
const save = useAdminAction('settings.save_guest_settings')

const { values, adopt, commit } = useSettingsAutosave(save)

watch(
  () => settings.data,
  (data) => data && adopt(data),
  { immediate: true },
)

watch(
  () => props.active,
  (isActive) => {
    if (isActive && !settings.isFinished) settings.reload()
  },
  { immediate: true },
)

const enabled = computed(() => Boolean(values.value.allow_guest_checkout))
</script>

<template>
  <SettingsPanelHeader
    title="Guest"
    description="Shoppers who buy without making an account."
  />

  <SettingsBody v-scroll-fade>
    <!-- A refused read must not read as "guest checkout is off". -->
    <EmptyState
      v-if="settings.error"
      compact
      icon="lucide-triangle-alert"
      title="This could not be loaded"
      description="Guest checkout may still be on. This panel just cannot say."
    >
      <Button label="Try again" variant="subtle" theme="gray" @click="settings.reload()" />
    </EmptyState>

    <SettingsSkeleton v-else-if="settings.loading && !settings.data" :rows="2" />

    <div v-else class="divide-y divide-outline-gray-1">
      <SettingsRow
        title="Allow guest checkout"
        description="Off, and shoppers sign in with an emailed code before they pay. Past guest orders stay viewable."
      >
        <Switch
          size="sm"
          :model-value="enabled"
          :disabled="save.loading"
          @update:model-value="commit('allow_guest_checkout', $event ? 1 : 0, 'Guest checkout')"
        />
      </SettingsRow>

      <SettingsRow
        v-if="enabled"
        title="Order link shows full details for (days)"
        description="The emailed order link shows the address and payment for this long, then only status and tracking. 0 means always."
      >
        <TextInput
          :model-value="values.guest_order_link_days"
          class="w-full sm:w-40"
          type="number"
          min="0"
          :disabled="save.loading"
          @change="commit('guest_order_link_days', $event.target.value, 'Order link days')"
        />
      </SettingsRow>
    </div>
  </SettingsBody>
</template>
