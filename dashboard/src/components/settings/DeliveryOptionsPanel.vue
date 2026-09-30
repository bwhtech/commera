<script setup>
import { computed, ref, watch } from 'vue'
import {
  Badge,
  Button,
  Dropdown,
  SettingsBody,
  dialog,
  toast,
} from 'frappe-ui'
import SettingsPanelHeader from './SettingsPanelHeader.vue'
import EmptyState from '../EmptyState.vue'
import DeliveryOptionConfig from './DeliveryOptionConfig.vue'
import DeliveryOptionRow from './DeliveryOptionRow.vue'
import ImportCarrierServicesDialog from './ImportCarrierServicesDialog.vue'
import SettingsSkeleton from './SettingsSkeleton.vue'
import { useDeliveryOptions } from '../../data/deliveryOptions'
import { isPriced, useShippingRates } from '../../data/shippingRates'

const props = defineProps({
  // Opening the Shipping tab should fetch; switching away and back should not.
  active: { type: Boolean, default: false },
})

const store = useDeliveryOptions()
const rates = useShippingRates()

// Only once the rates have loaded: before that every option would briefly read as hidden.
function isHidden(option) {
  return rates.loaded.value && !rates.loadError.value && !isPriced(rates.bandsFor(option.name), option)
}

// Two values: a new option has no row to name. A model, because the tab above has to know.
const editing = ref(null)
const editorOpen = defineModel('configuring', { type: Boolean, default: false })
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

function closeEditor() {
  editorOpen.value = false
  editing.value = null
}

// Handed to the screen rather than called by it, so it owns no knowledge of the
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
  <!-- In-panel, not a dialog: Settings never stacks a second modal. -->
  <DeliveryOptionConfig
    v-if="editorOpen"
    :option="editing"
    :groups="store.fieldGroups.value"
    :link-options-path="store.linkOptionsPath.value"
    :submit="saveOption"
    @back="closeEditor"
  />

  <template v-else>
    <SettingsPanelHeader
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
    </SettingsPanelHeader>

    <SettingsBody v-scroll-fade>
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
          :hidden="isHidden(option)"
          @edit="edit"
          @delete="confirmDelete"
          @toggle="toggle(option, $event)"
        />
      </div>
    </SettingsBody>

    <ImportCarrierServicesDialog
      v-model:open="importOpen"
      :provider="importProvider"
      :fetch-choices="store.carrierServices"
      :submit="importServices"
    />
  </template>
</template>
