<script setup>
import { computed, ref, watch } from 'vue'
import { Button, Select, SettingsBody, dialog } from 'frappe-ui'
import SettingsPanelHeader from './SettingsPanelHeader.vue'
import EmptyState from '../EmptyState.vue'
import SettingsSkeleton from './SettingsSkeleton.vue'
import ShippingRateOptionRow from './ShippingRateOptionRow.vue'
import ShippingRatesConfig from './ShippingRatesConfig.vue'
import { useDeliveryOptions } from '../../data/deliveryOptions'
import { RATE_BASES, useShippingRates } from '../../data/shippingRates'

const props = defineProps({
  active: { type: Boolean, default: false },
})

const UNTIED_TITLE = 'Not tied to an option'

const store = useShippingRates()
const deliveryOptions = useDeliveryOptions()

// Undefined while closed; null is the untied group, which is a real thing to edit.
const editing = ref(undefined)
const editorOpen = defineModel('configuring', { type: Boolean, default: false })

watch(() => props.active, (isActive) => isActive && store.loadOnce(), { immediate: true })

// An option added, renamed or switched off in the panel above changes what is listed here.
watch(deliveryOptions.options, () => store.loaded.value && store.load())

const optionTitles = computed(() =>
  Object.fromEntries(store.deliveryOptions.value.map((option) => [option.name, option.title])),
)

const untiedBands = computed(() => store.bandsFor(null))

const boundaryUnit = computed(() =>
  store.isWeightBased.value ? store.weightUom.value : store.currency.value,
)

const editingTitle = computed(() =>
  editing.value ? optionTitles.value[editing.value] ?? editing.value : UNTIED_TITLE,
)

function edit(shippingService) {
  editing.value = shippingService
  editorOpen.value = true
}

function closeEditor() {
  editorOpen.value = false
  editing.value = undefined
}

async function saveBands(bands) {
  return await store.mutate('save_service_rates', {
    shipping_service: editing.value ?? '',
    bands,
  })
}

function setBasis(value) {
  if (value === store.calculateBasedOn.value) return

  const change = () => store.mutate('set_rate_basis', { calculate_based_on: value })
  if (!store.bands.value.length) return change()

  const label = RATE_BASES.find((basis) => basis.value === value)?.label.toLowerCase()
  dialog.confirm({
    title: `Base shipping rates on ${label}?`,
    message: 'Every band keeps its numbers, so check each one reads right in the new unit.',
    confirmLabel: 'Switch',
    onConfirm: change,
  })
}
</script>

<template>
  <!-- In-panel, not a dialog: Settings never stacks a second modal. -->
  <ShippingRatesConfig
    v-if="editorOpen"
    :title="editingTitle"
    :shipping-service="editing"
    :bands="store.bandsFor(editing)"
    :other-bands="store.bands.value.filter((band) => (band.shipping_service || null) !== editing)"
    :option-titles="optionTitles"
    :boundary-unit="boundaryUnit"
    :currency="store.currency.value"
    :format-boundary="store.formatBoundary"
    :submit="saveBands"
    @back="closeEditor"
  />

  <template v-else>
    <SettingsPanelHeader
      title="Shipping rates"
      description="What each option costs. Unpriced options use the carrier."
    >
      <template #actions>
        <Select
          v-if="store.available.value && store.deliveryOptions.value.length"
          class="w-36"
          :model-value="store.calculateBasedOn.value"
          :options="RATE_BASES"
          :disabled="store.loading.value"
          aria-label="Shipping rates are based on"
          @update:model-value="setBasis"
        />
      </template>
    </SettingsPanelHeader>

    <SettingsBody v-scroll-fade>
      <EmptyState
        v-if="store.loadError.value"
        compact
        icon="lucide-triangle-alert"
        title="Shipping rates could not be loaded"
        description="Checkout still charges whatever is stored — this panel just cannot say what."
      >
        <Button label="Try again" variant="subtle" theme="gray" @click="store.load()" />
      </EmptyState>

      <SettingsSkeleton
        v-else-if="!store.loaded.value || (store.loading.value && !store.deliveryOptions.value.length)"
        :rows="2"
        :lines="2"
      />

      <EmptyState
        v-else-if="!store.available.value"
        compact
        icon="lucide-package"
        title="Shipping rates arrive with the shipping app"
        description="Install it to charge each delivery option by order value or weight."
      />

      <EmptyState
        v-else-if="!store.deliveryOptions.value.length"
        compact
        icon="lucide-receipt"
        title="Nothing to price yet"
        description="Add a delivery option above, then set what it costs here."
      />

      <div v-else class="divide-y divide-outline-gray-1">
        <ShippingRateOptionRow
          v-for="option in store.deliveryOptions.value"
          :key="option.name"
          :title="option.title"
          :option="option"
          :bands="store.bandsFor(option.name)"
          :format-boundary="store.formatBoundary"
          @edit="edit(option.name)"
        />
        <ShippingRateOptionRow
          v-if="untiedBands.length"
          :title="UNTIED_TITLE"
          :bands="untiedBands"
          :format-boundary="store.formatBoundary"
          @edit="edit(null)"
        />
      </div>
    </SettingsBody>
  </template>
</template>
