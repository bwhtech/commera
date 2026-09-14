<script setup>
/**
 * The price tables delivery options charge from — "₹99 under ₹999, free above".
 *
 * A third section under Shipping rather than a field on each option: one rate table is
 * usually shared by several options, and a band edited here reprices all of them.
 */
import { ref, watch } from 'vue'
import {
  Badge,
  Button,
  Dropdown,
  LoadingText,
  SettingsBody,
  SettingsHeader,
  dialog,
  toast,
} from 'frappe-ui'
import EmptyState from '../EmptyState.vue'
import ShippingRuleDialog from './ShippingRuleDialog.vue'
import { describeBands, useShippingRules } from '../../data/shippingRules'

const props = defineProps({
  active: { type: Boolean, default: false },
})

const store = useShippingRules()

const editing = ref(null)
const editorOpen = ref(false)

watch(() => props.active, (isActive) => isActive && store.loadOnce(), { immediate: true })

function create() {
  editing.value = null
  editorOpen.value = true
}

function edit(rule) {
  editing.value = rule
  editorOpen.value = true
}

async function saveRule(values) {
  return await store.mutate('save_shipping_rule', values)
}

function usageLine(rule) {
  const users = [...rule.used_by]
  if (rule.is_store_default) users.push('store default')
  return users.length ? `Used by ${users.join(', ')}` : ''
}

// Deleting a rule something still prices from is refused by the server, which names the
// options — that list is the useful part, so it is not second-guessed here.
function confirmDelete(rule) {
  dialog.confirm({
    title: `Delete ${rule.label}?`,
    message: 'Orders already placed keep the shipping they were charged.',
    theme: 'red',
    confirmLabel: 'Delete',
    onConfirm: async () => {
      const saved = await store.mutate('delete_shipping_rule', { name: rule.name })
      if (!saved) return
      toast.success(`${rule.label} deleted`)
    },
  })
}
</script>

<template>
  <SettingsHeader
    title="Shipping rates"
    description="Price bands a delivery option charges from, by cart value or weight."
  >
    <template #actions>
      <Button
        label="Add rate"
        icon-left="lucide-plus"
        variant="solid"
        theme="gray"
        @click="create"
      />
    </template>
  </SettingsHeader>

  <SettingsBody>
    <div v-if="store.loadError.value" class="py-6 text-base text-ink-gray-5">
      These could not be loaded.
      <Button label="Try again" variant="ghost" @click="store.load()" />
    </div>

    <LoadingText
      v-else-if="store.loading.value && !store.rules.value.length"
      class="py-6"
    />

    <EmptyState
      v-else-if="!store.rules.value.length"
      icon="lucide-truck"
      title="No shipping rates yet"
      description="Add one to charge a fixed price by cart value or weight — or ship free above an amount."
    >
      <Button label="Add rate" icon-left="lucide-plus" @click="create" />
    </EmptyState>

    <div v-else class="divide-y divide-outline-gray-1">
      <div v-for="rule in store.rules.value" :key="rule.name" class="flex items-center gap-3 py-3">
        <!-- min-w-0 lets the band line truncate instead of pushing the actions off the row. -->
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <p class="truncate text-base text-ink-gray-8">{{ rule.label }}</p>
            <Badge
              v-if="rule.calculate_based_on === 'Net Weight'"
              label="By weight"
              theme="gray"
              variant="subtle"
            />
            <Badge v-if="rule.disabled" label="Disabled" theme="orange" variant="subtle" />
          </div>
          <p class="mt-1 truncate text-sm text-ink-gray-5">
            {{ describeBands(rule) || 'No bands' }}
          </p>
          <p v-if="usageLine(rule)" class="mt-1 truncate text-sm text-ink-gray-5">
            {{ usageLine(rule) }}
          </p>
        </div>

        <div class="ml-auto flex shrink-0 items-center gap-2">
          <Button label="Edit" @click="edit(rule)" />
          <Dropdown
            :options="[
              {
                label: 'Delete',
                icon: 'lucide-trash-2',
                theme: 'red',
                onClick: () => confirmDelete(rule),
              },
            ]"
          >
            <Button icon="lucide-ellipsis" :aria-label="`More actions for ${rule.label}`" />
          </Dropdown>
        </div>
      </div>
    </div>
  </SettingsBody>

  <ShippingRuleDialog
    v-model:open="editorOpen"
    :rule="editing"
    :default-account="store.defaultAccount.value"
    :link-options-path="store.linkOptionsPath.value"
    :submit="saveRule"
  />
</template>
