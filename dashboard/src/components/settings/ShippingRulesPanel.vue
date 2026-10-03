<script setup>
import { computed, ref, watch } from 'vue'
import { Button, SettingsBody, dialog, toast } from 'frappe-ui'
import SettingsPanelHeader from './SettingsPanelHeader.vue'
import EmptyState from '../EmptyState.vue'
import SettingsSkeleton from './SettingsSkeleton.vue'
import ShippingRuleConfig from './ShippingRuleConfig.vue'
import ShippingRuleRow from './ShippingRuleRow.vue'
import { useDeliveryOptions } from '../../data/deliveryOptions'
import { useShippingRates } from '../../data/shippingRates'

const props = defineProps({
  active: { type: Boolean, default: false },
})

const store = useShippingRates()
const deliveryOptions = useDeliveryOptions()

// Two values: a new rule has no row to name. A model, because the tab above has to know.
const editing = ref(null)
const editorOpen = defineModel('configuring', { type: Boolean, default: false })

watch(() => props.active, (isActive) => isActive && store.loadOnce(), { immediate: true })

// An option added, renamed or switched off in the panel above changes what a band can name.
watch(deliveryOptions.options, () => store.loaded.value && store.load())

const optionTitles = computed(() =>
  Object.fromEntries(store.deliveryOptions.value.map((option) => [option.name, option.title])),
)

function create() {
  editing.value = null
  editorOpen.value = true
}

function edit(rule) {
  editing.value = rule
  editorOpen.value = true
}

function closeEditor() {
  editorOpen.value = false
  editing.value = null
}

async function saveRule(values) {
  return await store.mutate('save_shipping_rule', { name: editing.value?.name ?? '', ...values })
}

async function useAtCheckout(rule) {
  const { data } = await store.mutate('set_store_rule', { name: rule.name })
  if (data) toast.success(`Checkout now uses ${rule.label}`)
}

function confirmDelete(rule) {
  dialog.confirm({
    title: `Delete ${rule.label}?`,
    message: 'Its bands go with it. Orders already placed keep the shipping they were charged.',
    theme: 'red',
    confirmLabel: 'Delete',
    onConfirm: async () => {
      const { data } = await store.mutate('delete_shipping_rule', { name: rule.name })
      if (data) toast.success(`${rule.label} deleted`)
    },
  })
}
</script>

<template>
  <!-- In-panel, not a dialog: Settings never stacks a second modal. -->
  <ShippingRuleConfig
    v-if="editorOpen"
    :rule="editing"
    :in-use="Boolean(editing) && editing.name === store.storeRule.value"
    :delivery-options="store.deliveryOptions.value"
    :currency="store.currency.value"
    :submit="saveRule"
    @back="closeEditor"
  />

  <template v-else>
    <SettingsPanelHeader
      title="Shipping rules"
      description="The order-value bands checkout charges. Options with no matching band use their carrier rate or Backup Charge."
    >
      <template #actions>
        <Button
          v-if="store.available.value"
          label="Add rule"
          icon-left="lucide-plus"
          variant="solid"
          theme="gray"
          @click="create"
        />
      </template>
    </SettingsPanelHeader>

    <SettingsBody v-scroll-fade>
      <EmptyState
        v-if="store.loadError.value"
        compact
        icon="lucide-triangle-alert"
        title="Shipping rules could not be loaded"
        description="Checkout still charges whatever is stored — this panel just cannot say what."
      >
        <Button label="Try again" variant="subtle" theme="gray" @click="store.load()" />
      </EmptyState>

      <SettingsSkeleton
        v-else-if="!store.loaded.value || (store.loading.value && !store.rules.value.length)"
        :rows="2"
        :lines="2"
      />

      <EmptyState
        v-else-if="!store.available.value"
        compact
        icon="lucide-package"
        title="Shipping rules arrive with the shipping app"
        description="Install it to charge shipping by order value."
      />

      <EmptyState
        v-else-if="!store.rules.value.length"
        compact
        icon="lucide-receipt"
        title="No shipping rules yet"
        description="Add one to charge shipping by order value, per delivery option or for any of them."
      >
        <Button label="Add rule" icon-left="lucide-plus" variant="subtle" theme="gray" @click="create" />
      </EmptyState>

      <div v-else class="divide-y divide-outline-gray-1">
        <ShippingRuleRow
          v-for="rule in store.rules.value"
          :key="rule.name"
          :rule="rule"
          :in-use="rule.name === store.storeRule.value"
          :option-titles="optionTitles"
          @edit="edit"
          @use="useAtCheckout"
          @delete="confirmDelete"
        />
      </div>
    </SettingsBody>
  </template>
</template>
