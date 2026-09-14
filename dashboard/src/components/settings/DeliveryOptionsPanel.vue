<script setup>
/**
 * What a shopper is actually offered at checkout.
 *
 * The carrier cards above this are a connection — an account with keys. This is the other
 * half of the same story: the named, priced choices that connection makes possible. They
 * are kept apart because they change on different clocks. A carrier is connected once; the
 * options under it are renamed, repriced and switched off all week.
 *
 * A sibling of IntegrationsPanel rather than a mode of it: that panel is deliberately
 * generic and shared with Payments, and payments have no equivalent of this list.
 */
import { computed, ref, watch } from 'vue'
import {
  Badge,
  Button,
  Dropdown,
  SettingsBody,
  SettingsHeader,
  dialog,
  toast,
} from 'frappe-ui'
import EmptyState from '../EmptyState.vue'
import DeliveryOptionDialog from './DeliveryOptionDialog.vue'
import DeliveryOptionRow from './DeliveryOptionRow.vue'
import ImportCarrierServicesDialog from './ImportCarrierServicesDialog.vue'
import SettingsSkeleton from './SettingsSkeleton.vue'
import { useDeliveryOptions } from '../../data/deliveryOptions'

const props = defineProps({
  // Opening the Shipping tab should fetch; switching away and back should not.
  active: { type: Boolean, default: false },
})

const store = useDeliveryOptions()

const editing = ref(null)
const editorOpen = ref(false)
const importProvider = ref(null)
const importOpen = ref(false)

const importActions = computed(() =>
  store.importProviders.value.map((provider) => ({
    label: provider.label,
    onClick: () => {
      importProvider.value = provider
      importOpen.value = true
    },
  })),
)

watch(() => props.active, (isActive) => isActive && store.loadOnce(), { immediate: true })

function create() {
  editing.value = null
  editorOpen.value = true
}

function edit(option) {
  editing.value = option
  editorOpen.value = true
}

// Handed to the dialog rather than called by it, so the dialog owns no knowledge of the
// store — it collects answers and reports whether the save stuck.
async function saveOption(values) {
  return await store.mutate('save_delivery_option', { name: editing.value?.name ?? '', values })
}

async function importServices(provider, selections, defaultRate) {
  return await store.mutate('import_carrier_services', {
    provider,
    selections,
    default_rate: defaultRate,
  })
}

async function toggle(option, enabled) {
  // Enabling an option the server considers incomplete is refused there, which is also
  // where the reason lives — nothing is pre-empted here.
  const saved = await store.mutate('toggle_delivery_option', {
    name: option.name,
    enabled: enabled ? 1 : 0,
  })
  if (!saved) return

  toast.success(enabled ? `${option.title} is on` : `${option.title} is off`)
}

function confirmDelete(option) {
  dialog.confirm({
    title: `Delete ${option.title}?`,
    message:
      'Shoppers stop being offered it at checkout. Orders already placed with it keep the name they were placed under.',
    theme: 'red',
    confirmLabel: 'Delete',
    onConfirm: async () => {
      const saved = await store.mutate('delete_delivery_option', { name: option.name })
      if (!saved) return
      toast.success(`${option.title} deleted`)
    },
  })
}
</script>

<template>
  <SettingsHeader
    title="Delivery options"
    description="What shoppers pick at checkout."
  >
    <template #actions>
      <Badge
        v-if="store.options.value.length"
        :label="`${store.enabledCount.value} of ${store.options.value.length} on`"
        theme="gray"
        variant="subtle"
      />
      <Dropdown v-if="store.available.value && importActions.length" :options="importActions">
        <Button label="Import from carrier" icon-right="lucide-chevron-down" />
      </Dropdown>
      <Button
        v-if="store.available.value"
        label="Add option"
        icon-left="lucide-plus"
        variant="solid"
        theme="gray"
        @click="create"
      />
    </template>
  </SettingsHeader>

  <SettingsBody>
    <!-- A refused read must not read as "this store has no delivery options". -->
    <EmptyState
      v-if="store.loadError.value"
      compact
      icon="lucide-triangle-alert"
      title="These could not be loaded"
      description="Shoppers are still offered whatever is stored — this panel just cannot say what."
    >
      <Button label="Try again" variant="subtle" theme="gray" @click="store.load()" />
    </EmptyState>

    <!-- Three lines, because an option row carries its name, its description and its price. -->
    <SettingsSkeleton
      v-else-if="store.loading.value && !store.options.value.length"
      :rows="3"
      :lines="3"
    />

    <!-- The app that defines a shipping service is not installed, so there is nothing to
         list and nothing to create — this is a state of the site, not a failure. -->
    <EmptyState
      v-else-if="!store.available.value"
      compact
      icon="lucide-package"
      title="Delivery options arrive with the shipping app"
      description="Install it to offer shoppers a choice at checkout; until then every order ships on whatever your carrier quotes."
    />

    <EmptyState
      v-else-if="!store.options.value.length"
      compact
      icon="lucide-truck"
      title="Checkout offers nothing to pick"
      description="There are no delivery options yet. Import the services a connected carrier sells, or add one of your own."
    />

    <div v-else class="divide-y divide-outline-gray-1">
      <DeliveryOptionRow
        v-for="option in store.options.value"
        :key="option.name"
        :option="option"
        :busy="store.loading.value"
        @edit="edit"
        @delete="confirmDelete"
        @toggle="toggle(option, $event)"
      />
    </div>
  </SettingsBody>

  <DeliveryOptionDialog
    v-model:open="editorOpen"
    :option="editing"
    :groups="store.fieldGroups.value"
    :link-options-path="store.linkOptionsPath.value"
    :submit="saveOption"
  />

  <ImportCarrierServicesDialog
    v-model:open="importOpen"
    :provider="importProvider"
    :fetch-choices="store.carrierServices"
    :submit="importServices"
  />
</template>
