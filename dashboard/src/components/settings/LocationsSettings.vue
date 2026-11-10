<script setup>
import { computed, ref, watch } from 'vue'
import {
  Badge,
  Button,
  SettingsBody,
  SettingsRow,
  Switch,
  toast,
} from 'frappe-ui'
import SettingsPanelHeader from './SettingsPanelHeader.vue'
import EmptyState from '../EmptyState.vue'
import PickupAddressConfig from './PickupAddressConfig.vue'
import SettingsSkeleton from './SettingsSkeleton.vue'
import { pickupLocations } from '../../data/pickupLocations'
import { onSettingsClose } from '../../ia/settings'
import { __ } from '../../data/translation'

const props = defineProps({
  active: { type: Boolean, default: false },
})

const { screen, loadError, loading: saving, pickupEnabled, warehouses, mutate } = pickupLocations

// The warehouse whose address is open, by name: the row itself is replaced by every answer the
// server gives, so a held object would go stale the moment a switch is flipped.
const editing = ref(null)
const current = computed(
  () => warehouses.value.find((warehouse) => warehouse.name === editing.value) ?? null,
)

watch(() => props.active, (isActive) => isActive && pickupLocations.loadOnce(), { immediate: true })
onSettingsClose(() => (editing.value = null))

async function toggleStorePickup(enabled) {
  if (!(await mutate('save_store_pickup', { enabled: enabled ? 1 : 0 }))) return
  toast.success(enabled ? __('Store pickup is on') : __('Store pickup is off'))
}

async function toggleWarehouse(warehouse, allowPickup) {
  const saved = await mutate('save_warehouse_pickup', {
    warehouse: warehouse.name,
    allow_pickup: allowPickup ? 1 : 0,
  })
  if (!saved) return
  toast.success(
    allowPickup
      ? __('Pickup allowed at {0}', [warehouse.warehouse_name])
      : __('Pickup stopped at {0}', [warehouse.warehouse_name]),
  )
}

async function saveAddress(values) {
  const hadAddress = Boolean(current.value.address)
  if (!(await mutate('save_pickup_address', { warehouse: current.value.name, values }))) return

  editing.value = null
  toast.success(hadAddress ? __('Pickup address saved') : __('Pickup address added'))
}
</script>

<template>
  <PickupAddressConfig
    v-if="current"
    :warehouse="current"
    :saving="saving"
    @back="editing = null"
    @save="saveAddress"
  />

  <template v-else>
    <SettingsPanelHeader
      :title="__('Pickup locations')"
      :description="__('Your warehouses, and where shoppers can collect their order.')"
    />

    <SettingsBody v-scroll-fade>
      <EmptyState
        v-if="loadError && !screen"
        compact
        icon="lucide-triangle-alert"
        :title="__('These could not be loaded')"
        :description="__('Checkout still offers whatever is stored — this panel just cannot say what.')"
      >
        <Button :label="__('Try again')" variant="subtle" theme="gray" @click="pickupLocations.load()" />
      </EmptyState>

      <SettingsSkeleton v-else-if="!screen" :rows="3" />

      <template v-else>
        <SettingsRow
          :title="__('Store pickup')"
          :description="__('Let shoppers collect their order from a warehouse instead of having it delivered.')"
        >
          <Switch
            size="sm"
            :model-value="pickupEnabled"
            :disabled="saving"
            @update:model-value="toggleStorePickup"
          />
        </SettingsRow>

        <!-- Which warehouses take pickups is only worth asking once pickup is on, the same way the
             Analytics tab keeps a service's ids hidden until its switch is. -->
        <EmptyState
          v-if="pickupEnabled && !warehouses.length"
          compact
          icon="lucide-warehouse"
          :title="__('No warehouses yet')"
          :description="__('Add a warehouse in your books, and it shows up here.')"
        />

        <div v-else-if="pickupEnabled" class="divide-y divide-outline-gray-1 border-t border-outline-gray-1">
          <div
            v-for="warehouse in warehouses"
            :key="warehouse.name"
            class="flex items-start gap-3 py-3"
          >
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <p class="truncate text-base text-ink-gray-8">{{ warehouse.warehouse_name }}</p>
                <Badge
                  v-if="warehouse.is_ecommerce_warehouse"
                  :label="__('Online orders')"
                  theme="gray"
                  variant="subtle"
                />
              </div>
              <p class="mt-1 truncate text-sm text-ink-gray-5">{{ warehouse.company }}</p>

              <template v-if="warehouse.allow_pickup">
                <p v-if="warehouse.address" class="mt-1 text-sm text-ink-gray-6">
                  {{ warehouse.address.display }}
                  <span
                    v-if="!warehouse.address.custom_store_location"
                    class="text-ink-gray-5"
                  > · {{ __('No map pin') }}</span>
                </p>
                <!-- Checkout skips a pickup warehouse it has nowhere to send the shopper to, so this
                     is the only place the owner learns why it is missing. -->
                <Badge
                  v-else
                  class="mt-1.5"
                  :label="__('Needs an address — hidden at checkout')"
                  theme="amber"
                  variant="subtle"
                />
              </template>
            </div>

            <div class="flex shrink-0 items-center gap-2">
              <Button
                v-if="warehouse.allow_pickup"
                :label="warehouse.address ? __('Edit address') : __('Add address')"
                @click="editing = warehouse.name"
              />
              <Switch
                size="sm"
                :model-value="Boolean(warehouse.allow_pickup)"
                :disabled="saving"
                @update:model-value="toggleWarehouse(warehouse, $event)"
              />
            </div>
          </div>
        </div>
      </template>
    </SettingsBody>
  </template>
</template>
