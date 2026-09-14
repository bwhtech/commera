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
import DeliveryOptionDialog from './DeliveryOptionDialog.vue'
import DeliveryOptionRow from './DeliveryOptionRow.vue'
import ImportCarrierServicesDialog from './ImportCarrierServicesDialog.vue'
import ShippingRuleDialog from './ShippingRuleDialog.vue'
import { useDeliveryOptions } from '../../data/deliveryOptions'
import { useShippingRules } from '../../data/shippingRules'

const props = defineProps({
  // Opening the Shipping tab should fetch; switching away and back should not.
  active: { type: Boolean, default: false },
})

const store = useDeliveryOptions()

const editing = ref(null)
const editorOpen = ref(false)
const importProvider = ref(null)
const importOpen = ref(false)

// The shared store, so a rate made from an option's form is already listed in the Shipping
// rates section below when the form closes.
const shippingRules = useShippingRules()
const rateEditorOpen = ref(false)
let setRateOnOption = null

async function openRateEditor(setValue) {
  setRateOnOption = setValue
  await shippingRules.loadOnce()
  rateEditorOpen.value = true
}

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
    <div v-if="store.loadError.value" class="py-6 text-base text-ink-gray-5">
      These could not be loaded.
      <Button label="Try again" variant="ghost" @click="store.load()" />
    </div>

    <div
      v-else-if="store.loading.value && !store.options.value.length"
      class="py-6 text-base text-ink-gray-5"
    >
      Loading…
    </div>

    <!-- The app that defines a shipping service is not installed, so there is nothing to
         list and nothing to create — this is a state of the site, not a failure. -->
    <p v-else-if="!store.available.value" class="py-6 text-p-base text-ink-gray-5">
      Delivery options arrive with the shipping app. Install it to offer shoppers a choice at
      checkout; until then every order ships on whatever your carrier quotes.
    </p>

    <p v-else-if="!store.options.value.length" class="py-6 text-p-base text-ink-gray-5">
      No delivery options yet, so checkout offers nothing to pick. Import the services a
      connected carrier sells, or add one of your own.
    </p>

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
  >
    <template #after-fields="{ setValue }">
      <div class="pt-3">
        <Button
          label="New shipping rate"
          icon-left="lucide-plus"
          variant="ghost"
          @click="openRateEditor(setValue)"
        />
      </div>
    </template>
  </DeliveryOptionDialog>

  <ShippingRuleDialog
    v-model:open="rateEditorOpen"
    :default-account="shippingRules.defaultAccount.value"
    :link-options-path="shippingRules.linkOptionsPath.value"
    :submit="(values) => shippingRules.mutate('save_shipping_rule', values)"
    @saved="(label) => setRateOnOption?.('shipping_rule', label)"
  />

  <ImportCarrierServicesDialog
    v-model:open="importOpen"
    :provider="importProvider"
    :fetch-choices="store.carrierServices"
    :submit="importServices"
  />
</template>
