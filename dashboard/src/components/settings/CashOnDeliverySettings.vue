<script setup>
/**
 * Cash on delivery: the one payment method the store settles itself.
 *
 * It sits under the gateway cards rather than beside them because it is not a connection —
 * there are no keys and nothing to test. It is a switch and two amounts, so it reads as the
 * second half of the Payments story the way delivery options do for Shipping.
 *
 * Every control saves itself, the way the theme fields do: committed on change rather than
 * per keystroke, so a half-typed amount is never written.
 */
import { computed, ref, watch } from 'vue'
import {
  Button,
  SettingsBody,
  SettingsHeader,
  SettingsRow,
  Switch,
  TextInput,
  toast,
} from 'frappe-ui'
import EmptyState from '../EmptyState.vue'
import SettingsLinkControl from './SettingsLinkControl.vue'
import SettingsSkeleton from './SettingsSkeleton.vue'
import { useAdminAction, useAdminRead } from '../../data/api'

const props = defineProps({
  // Opening the Payments tab should fetch; switching away and back should not.
  active: { type: Boolean, default: false },
})

const ACCOUNT_FIELD = { fieldname: 'charge_account_head', options: 'Account' }

const settings = useAdminRead('settings.get_payment_settings', { immediate: false })
const save = useAdminAction('settings.save_payment_settings')

// What is in the boxes, and what the server last said was stored. Every answer the server gives
// is adopted into both, so a value it rewrote — or a save it refused — wins over what was typed.
const values = ref({})
const stored = ref({})

function adopt(record) {
  stored.value = { ...record }
  values.value = { ...record }
}

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

const enabled = computed(() => Boolean(values.value.cod_enabled))

// Frappe stores checks as 1/0 and currency as a number, while an input hands back a string:
// two values are the same when they would be stored the same.
function unchanged(fieldname, value) {
  const before = stored.value[fieldname]
  return String(value ?? '') === String(before ?? '')
}

async function commit(fieldname, value, label) {
  if (unchanged(fieldname, value)) return

  values.value[fieldname] = value
  const saved = await save.submit({ [fieldname]: value })
  if (save.error) {
    // The write is the only truth; a refused one must not leave the box showing what it refused.
    values.value = { ...stored.value }
    return
  }

  adopt(saved)
  toast.success(`${label} saved`)
}

function commitNumber(fieldname, event, label) {
  commit(fieldname, event.target.value, label)
}
</script>

<template>
  <SettingsHeader
    title="Cash on delivery"
    description="Taking payment at the door, and what it costs to offer it."
  />

  <SettingsBody>
    <!-- A refused read must not read as "cash on delivery is off". -->
    <EmptyState
      v-if="settings.error"
      compact
      icon="lucide-triangle-alert"
      title="This could not be loaded"
      description="Cash on delivery may still be on — this panel just cannot say."
    >
      <Button label="Try again" variant="subtle" theme="gray" @click="settings.reload()" />
    </EmptyState>

    <SettingsSkeleton v-else-if="settings.loading && !settings.data" :rows="4" />

    <div v-else class="divide-y divide-outline-gray-1">
      <SettingsRow
        title="Offer cash on delivery"
        description="Off, and checkout stops offering it — placed orders are unaffected."
      >
        <Switch
          size="sm"
          :model-value="enabled"
          :disabled="save.loading"
          @update:model-value="commit('cod_enabled', $event ? 1 : 0, 'Cash on delivery')"
        />
      </SettingsRow>

      <!-- What it costs to offer COD is only worth asking while it is offered. -->
      <template v-if="enabled">
        <SettingsRow title="COD charge" description="Added to the order when the fee applies.">
          <TextInput
            :model-value="values.cod_charge"
            class="w-40"
            type="number"
            :disabled="save.loading"
            @change="commitNumber('cod_charge', $event, 'COD charge')"
          />
        </SettingsRow>

        <SettingsRow
          title="Charge below order value"
          description="The fee applies under this total, so bigger baskets carry no COD charge. Leave both at zero to never charge for it."
        >
          <TextInput
            :model-value="values.cod_charge_applicable_below"
            class="w-40"
            type="number"
            :disabled="save.loading"
            @change="commitNumber('cod_charge_applicable_below', $event, 'Order value')"
          />
        </SettingsRow>
      </template>

      <!-- Not COD's own, so it outlives the switch: the delivery charge posts here too, and
           hiding it with the rest would make that unreachable whenever COD is off. -->
      <SettingsRow
        title="Charge account"
        description="Where the COD and delivery charges post in your books."
      >
        <SettingsLinkControl
          :field="ACCOUNT_FIELD"
          :model-value="values.charge_account_head ?? ''"
          options-path="settings.get_link_options"
          class="w-72"
          @update:model-value="commit('charge_account_head', $event, 'Charge account')"
        />
      </SettingsRow>
    </div>
  </SettingsBody>
</template>
