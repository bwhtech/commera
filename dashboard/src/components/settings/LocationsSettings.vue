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

async function toggleStorePickup(enabled) {
  if (!(await mutate('save_store_pickup', { enabled: enabled ? 1 : 0 }))) return
  toast.success(enabled ? 'Store pickup is on' : 'Store pickup is off')
}

async function toggleWarehouse(warehouse, allowPickup) {
  const saved = await mutate('save_warehouse_pickup', {
    warehouse: warehouse.name,
    allow_pickup: allowPickup ? 1 : 0,
  })
  if (!saved) return
  toast.success(`Pickup ${allowPickup ? 'allowed' : 'stopped'} at ${warehouse.warehouse_name}`)
}

async function saveAddress(values) {
  const hadAddress = Boolean(current.value.address)
  if (!(await mutate('save_pickup_address', { warehouse: current.value.name, values }))) return

  editing.value = null
  toast.success(hadAddress ? 'Pickup address saved' : 'Pickup address added')
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
      title="Pickup locations"
      description="Your warehouses, and where shoppers can collect their order."
    />

    <SettingsBody v-scroll-fade>
      <EmptyState
        v-if="loadError && !screen"
        compact
        icon="lucide-triangle-alert"
        title="These could not be loaded"
        description="Checkout still offers whatever is stored — this panel just cannot say what."
      >
        <Button label="Try again" variant="subtle" theme="gray" @click="pickupLocations.load()" />
      </EmptyState>

      <SettingsSkeleton v-else-if="!screen" :rows="3" />

      <template v-else>
        <SettingsRow
          title="Store pickup"
          description="Let shoppers collect their order from a warehouse instead of having it delivered."
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
          title="No warehouses yet"
          description="Add a warehouse in your books, and it shows up here."
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
                  label="Online orders"
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
                  > · No map pin</span>
                </p>
                <!-- Checkout skips a pickup warehouse it has nowhere to send the shopper to, so this
                     is the only place the owner learns why it is missing. -->
                <Badge
                  v-else
                  class="mt-1.5"
                  label="Needs an address — hidden at checkout"
                  theme="amber"
                  variant="subtle"
                />
              </template>
            </div>

            <div class="flex shrink-0 items-center gap-2">
              <Button
                v-if="warehouse.allow_pickup"
                :label="warehouse.address ? 'Edit address' : 'Add address'"
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
