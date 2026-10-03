<script setup>
import { computed, ref, useId } from 'vue'
import {
  Button,
  Checkbox,
  FormControl,
  Select,
  SettingsBody,
  SettingsRow,
  Switch,
  TextInput,
  toast,
} from 'frappe-ui'
import SettingsConfigHeader from './SettingsConfigHeader.vue'
import { errorMessage } from '../../data/errors'
import { findBandConflicts, formatBandRange } from '../../data/shippingRates'

const props = defineProps({
  // Null while creating; the rule being edited otherwise.
  rule: { type: Object, default: null },
  inUse: { type: Boolean, default: false },
  deliveryOptions: { type: Array, default: () => [] },
  currency: { type: String, default: '' },
  submit: { type: Function, required: true },
})

const emit = defineEmits(['back'])

// The From and To boxes need room for a five-digit value; below that 1fr collapses to nothing.
const GRID =
  'grid grid-cols-3 items-center gap-2 sm:grid-cols-[minmax(4.5rem,1fr)_minmax(4.5rem,1fr)_minmax(5rem,1fr)_auto_minmax(8rem,1.5fr)_auto]'

// The submit button sits outside the form, so `form` is what runs the name's `required`.
const formId = useId()

const isEdit = computed(() => Boolean(props.rule))

// '' is the "Any option" row: a band that names no delivery option.
const optionChoices = computed(() => [
  { label: 'Any option', value: '' },
  ...props.deliveryOptions.map((option) => ({ label: option.title, value: option.name })),
])

let nextKey = 0
const toRow = (band) => ({
  key: nextKey++,
  from_value: band.from_value ?? 0,
  // A stored 0 means "and above", which reads as an empty box, not as a limit of zero.
  to_value: Number(band.to_value) ? band.to_value : '',
  shipping_amount: band.shipping_amount ?? 0,
  free_shipping: Boolean(band.free_shipping),
  shipping_service: band.shipping_service ?? '',
})

const label = ref('')
const useAtCheckout = ref(props.inUse)
const rows = ref((props.rule?.bands ?? []).map(toRow))
const saving = ref(false)
const serverError = ref('')

function addRow() {
  const highestTo = Math.max(0, ...rows.value.map((row) => Number(row.to_value) || 0))
  // ERPNext's convention: a band starts one unit past the previous To, which is inclusive.
  const from = highestTo ? highestTo + 1 : 0
  rows.value.push(toRow({ from_value: from, to_value: 0, shipping_amount: 0 }))
}

function removeRow(key) {
  rows.value = rows.value.filter((row) => row.key !== key)
}

function describeConflict({ kind, bands }) {
  if (kind === 'order') return 'Each band has to start below where it ends.'
  if (kind === 'open') return 'Only one band can be left open-ended.'
  return `${bands.map(formatBandRange).join(' and ')} overlap.`
}

const conflictMessages = computed(() => [...new Set(findBandConflicts(rows.value).map(describeConflict))])

async function save() {
  saving.value = true
  serverError.value = ''
  try {
    const conditions = rows.value.map((row) => ({
      from_value: Number(row.from_value) || 0,
      to_value: Number(row.to_value) || 0,
      shipping_amount: row.free_shipping ? 0 : Number(row.shipping_amount) || 0,
      free_shipping: row.free_shipping ? 1 : 0,
      shipping_service: row.shipping_service || '',
    }))
    // The server refuses a label on an edit: it is the rule's name.
    const payload = {
      conditions,
      use_at_checkout: useAtCheckout.value ? 1 : 0,
      ...(isEdit.value ? {} : { label: label.value.trim() }),
    }
    const { data, error } = await props.submit(payload)
    if (!data) {
      serverError.value = errorMessage(error)
      return
    }

    toast.success(isEdit.value ? 'Shipping rule saved' : 'Shipping rule added')
    emit('back')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <SettingsConfigHeader
    :title="isEdit ? rule.label : 'Add a shipping rule'"
    description="Checkout charges the band the order total falls in. Leave To blank for “and above”."
    @back="emit('back')"
  >
    <template #actions>
      <Button
        type="submit"
        :form="formId"
        variant="solid"
        theme="gray"
        :loading="saving"
        :disabled="conflictMessages.length > 0"
        :label="isEdit ? 'Save' : 'Add'"
      />
    </template>
  </SettingsConfigHeader>

  <SettingsBody v-scroll-fade>
    <form :id="formId" @submit.prevent="save">
      <div class="divide-y divide-outline-gray-1">
        <SettingsRow
          v-if="isEdit"
          title="Name"
          description="The rule is stored under this name, so it cannot be changed."
        >
          <p class="w-72 text-base text-ink-gray-7">{{ rule.label }}</p>
        </SettingsRow>

        <div v-else class="py-3.5">
          <FormControl
            v-model="label"
            label="Name"
            required
            placeholder="Standard shipping"
            description="Only you see it. It cannot be changed later."
          />
        </div>

        <SettingsRow
          title="Use at checkout"
          :description="
            inUse
              ? 'Checkout charges these bands. Switch another rule on to stop using this one.'
              : 'On, and checkout charges these bands instead of the rule it uses now.'
          "
        >
          <Switch v-model="useAtCheckout" size="sm" :disabled="inUse" />
        </SettingsRow>

        <div class="flex flex-col gap-2 py-3">
          <!-- One grid for the headings and every band, so the columns line up. -->
          <div v-if="rows.length" :class="GRID">
            <span class="text-sm text-ink-gray-5">From ({{ currency }})</span>
            <span class="text-sm text-ink-gray-5">To ({{ currency }})</span>
            <span class="text-sm text-ink-gray-5">Charge{{ currency ? ` (${currency})` : '' }}</span>
            <span class="hidden sm:block" aria-hidden="true" />
            <span class="hidden text-sm text-ink-gray-5 sm:block">Delivery option</span>
            <span class="hidden sm:block" aria-hidden="true" />

            <template v-for="(row, index) in rows" :key="row.key">
              <TextInput
                v-model="row.from_value"
                type="number"
                min="0"
                step="0.01"
                :aria-label="`Band ${index + 1} from`"
              />
              <TextInput
                v-model="row.to_value"
                type="number"
                min="0"
                step="0.01"
                placeholder="and above"
                :aria-label="`Band ${index + 1} to`"
              />
              <TextInput
                v-model="row.shipping_amount"
                type="number"
                min="0"
                step="0.01"
                :disabled="row.free_shipping"
                :aria-label="`Band ${index + 1} charge`"
              />
              <!-- Below sm the six columns overflow a phone, so Free, the option and remove drop to their own line. -->
              <div class="col-span-3 flex items-center gap-2 sm:contents">
                <Checkbox v-model="row.free_shipping" label="Free" />
                <Select
                  v-model="row.shipping_service"
                  class="w-full min-w-0"
                  :options="optionChoices"
                  :aria-label="`Band ${index + 1} delivery option`"
                />
                <Button
                  icon="lucide-x"
                  variant="ghost"
                  :aria-label="`Remove band ${index + 1}`"
                  @click="removeRow(row.key)"
                />
              </div>
            </template>
          </div>

          <p v-if="!rows.length" class="text-p-sm text-ink-gray-5">
            No bands yet. Add one for each range of order totals you charge differently.
          </p>

          <div>
            <Button label="Add band" icon-left="lucide-plus" variant="subtle" theme="gray" @click="addRow" />
          </div>

          <p
            v-for="message in [...conflictMessages, ...(serverError ? [serverError] : [])]"
            :key="message"
            class="flex items-start gap-1.5 text-p-sm text-ink-red-6"
            role="alert"
          >
            <span class="lucide-circle-alert mt-0.5 size-4 shrink-0" aria-hidden="true" />
            {{ message }}
          </p>
        </div>
      </div>
    </form>
  </SettingsBody>
</template>
