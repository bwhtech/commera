<script setup>
import { computed } from 'vue'
import {
  Button,
  SettingsBody,
  SettingsRow,
  Switch,
  TextInput,
} from 'frappe-ui'
import SettingsPanelHeader from './SettingsPanelHeader.vue'
import EmptyState from '../EmptyState.vue'
import SettingsLinkControl from './SettingsLinkControl.vue'
import SettingsSkeleton from './SettingsSkeleton.vue'
import { useSettingsTab } from '../../data/useSettingsTab'

const props = defineProps({
  // Opening the Payments tab should fetch; switching away and back should not.
  active: { type: Boolean, default: false },
})

const ACCOUNT_FIELD = { fieldname: 'charge_account_head', options: 'Account' }

const { settings, save, values, commit } = useSettingsTab('payments', () => props.active)

const enabled = computed(() => Boolean(values.value.cod_enabled))

function commitNumber(fieldname, event, label) {
  commit(fieldname, event.target.value, label)
}
</script>

<template>
  <SettingsPanelHeader :title="__('Cash on delivery')" />

  <SettingsBody v-scroll-fade>
    <!-- A refused read must not read as "cash on delivery is off". -->
    <EmptyState
      v-if="settings.error"
      compact
      icon="lucide-triangle-alert"
      :title="__('This could not be loaded')"
      :description="__('Cash on delivery may still be on.')"
    >
      <Button :label="__('Try again')" variant="subtle" theme="gray" @click="settings.reload()" />
    </EmptyState>

    <SettingsSkeleton v-else-if="settings.loading && !settings.data" :rows="4" />

    <div v-else class="divide-y divide-outline-gray-1">
      <SettingsRow :title="__('Offer cash on delivery')">
        <Switch
          size="sm"
          :model-value="enabled"
          :disabled="save.loading"
          @update:model-value="commit('cod_enabled', $event ? 1 : 0, __('Cash on delivery'))"
        />
      </SettingsRow>

      <!-- What it costs to offer COD is only worth asking while it is offered. -->
      <template v-if="enabled">
        <SettingsRow :title="__('COD charge')">
          <TextInput
            :model-value="values.cod_charge"
            class="w-full sm:w-40"
            type="number"
            :disabled="save.loading"
            @change="commitNumber('cod_charge', $event, __('COD charge'))"
          />
        </SettingsRow>

        <SettingsRow
          :title="__('Charge below order value')"
          :description="__('Orders up to this total pay the COD charge. Leave at 0 to never charge it.')"
        >
          <TextInput
            :model-value="values.cod_charge_applicable_below"
            class="w-full sm:w-40"
            type="number"
            :disabled="save.loading"
            @change="commitNumber('cod_charge_applicable_below', $event, __('Order value'))"
          />
        </SettingsRow>
      </template>

      <!-- Not COD's own, so it outlives the switch: the delivery charge posts here too, and
           hiding it with the rest would make that unreachable whenever COD is off. -->
      <SettingsRow
        :title="__('Charge account')"
        :description="__('Delivery charges post here too.')"
      >
        <SettingsLinkControl
          :field="ACCOUNT_FIELD"
          :model-value="values.charge_account_head ?? ''"
          options-path="settings.get_link_options"
          class="w-full sm:w-72"
          @update:model-value="commit('charge_account_head', $event, __('Charge account'))"
        />
      </SettingsRow>
    </div>
  </SettingsBody>
</template>
