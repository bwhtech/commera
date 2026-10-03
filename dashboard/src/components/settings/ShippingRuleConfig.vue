<script setup>
import { computed, ref, useId } from 'vue'
import {
  Badge,
  Button,
  FormControl,
  Select,
  SettingsBody,
  SettingsRow,
  Switch,
  TabButtons,
  TextInput,
  toast,
} from 'frappe-ui'
import SettingsConfigHeader from './SettingsConfigHeader.vue'
import { errorMessage } from '../../data/errors'
import { currencySymbol, exactMoney } from '../../data/format'
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

const CHARGE_KINDS = [
  { label: 'Amount', value: 'amount' },
  { label: 'Free', value: 'free' },
]

// The submit button sits outside the form, so `form` is what runs the name's `required`.
const formId = useId()

const isEdit = computed(() => Boolean(props.rule))
const moneyPrefix = currencySymbol || props.currency

// '' is the "Any option" row: a band that names no delivery option.
const optionChoices = computed(() => [
  { label: 'Any option', value: '' },
  ...props.deliveryOptions.map((option) => ({ label: option.title, value: option.name })),
])

const optionTitles = computed(() =>
  Object.fromEntries(props.deliveryOptions.map((option) => [option.name, option.title])),
)

let nextKey = 0
const toRow = (band) => ({
  key: nextKey++,
  from_value: Number(band.from_value) || 0,
  // 0 means "and above".
  to_value: Number(band.to_value) || 0,
  shipping_amount: Number(band.shipping_amount) || 0,
  free_shipping: Boolean(band.free_shipping),
  shipping_service: band.shipping_service ?? '',
})

const label = ref('')
const useAtCheckout = ref(props.inUse)
const rows = ref((props.rule?.bands ?? []).map(toRow))
const saving = ref(false)
const serverError = ref('')

// The one band open for editing, as a draft; the list keeps the saved copy until Done.
const draft = ref(null)
const draftIsNew = ref(false)

function toDraft(row) {
  return {
    key: row.key,
    from_value: String(row.from_value),
    to_value: row.to_value ? String(row.to_value) : '',
    shipping_amount: String(row.shipping_amount),
    charge: row.free_shipping ? 'free' : 'amount',
    shipping_service: row.shipping_service,
  }
}

function fromDraft(band) {
  return {
    key: band.key,
    from_value: Number(band.from_value) || 0,
    to_value: Number(band.to_value) || 0,
    shipping_amount: band.charge === 'free' ? 0 : Number(band.shipping_amount) || 0,
    free_shipping: band.charge === 'free',
    shipping_service: band.shipping_service,
  }
}

function editRow(row) {
  if (draft.value) return
  draft.value = toDraft(row)
  draftIsNew.value = false
}

function addRow() {
  if (draft.value) return
  const highestTo = Math.max(0, ...rows.value.map((row) => row.to_value))
  // ERPNext's convention: a band starts one unit past the previous To, which is inclusive.
  const row = toRow({ from_value: highestTo ? highestTo + 1 : 0 })
  rows.value.push(row)
  draft.value = toDraft(row)
  draftIsNew.value = true
}

function closeDraft() {
  draft.value = null
  draftIsNew.value = false
}

function cancelDraft() {
  if (draftIsNew.value) removeRow(draft.value.key)
  closeDraft()
}

function removeRow(key) {
  rows.value = rows.value.filter((row) => row.key !== key)
  if (draft.value?.key === key) closeDraft()
}

function describeConflict({ kind, bands }) {
  if (kind === 'order') return 'Each band has to start below where it ends.'
  if (kind === 'open') return 'Only one band can be left open-ended.'
  return `${bands.map((band) => formatBandRange(band)).join(' and ')} overlap.`
}

// ERPNext checks the whole rule, so the draft is checked against every other band.
const draftConflicts = computed(() => {
  if (!draft.value) return []
  const others = rows.value.filter((row) => row.key !== draft.value.key)
  const candidate = { ...fromDraft(draft.value), draft: true }
  const conflicts = findBandConflicts([candidate, ...others]).filter((conflict) =>
    conflict.bands.some((band) => band.draft),
  )
  return [...new Set(conflicts.map(describeConflict))]
})

function applyDraft() {
  if (draftConflicts.value.length) return
  const updated = fromDraft(draft.value)
  rows.value = rows.value
    .map((row) => (row.key === updated.key ? updated : row))
    .sort((first, second) => first.from_value - second.from_value)
  closeDraft()
}

// While a band is open its header follows the draft, so the summary reads what Done will keep.
function shown(row) {
  return draft.value?.key === row.key ? fromDraft(draft.value) : row
}

function optionLabel(row) {
  if (!row.shipping_service) return 'Any option'
  return optionTitles.value[row.shipping_service] ?? row.shipping_service
}

function chargeText(row) {
  return row.free_shipping ? null : exactMoney(row.shipping_amount)
}

async function save() {
  saving.value = true
  serverError.value = ''
  try {
    const conditions = rows.value.map((row) => ({
      from_value: row.from_value,
      to_value: row.to_value,
      shipping_amount: row.free_shipping ? 0 : row.shipping_amount,
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
    description="Checkout charges the band the order total falls in."
    @back="emit('back')"
  >
    <template #actions>
      <Button
        type="submit"
        :form="formId"
        variant="solid"
        theme="gray"
        :loading="saving"
        :disabled="Boolean(draft)"
        :label="isEdit ? 'Save' : 'Add'"
      />
    </template>
  </SettingsConfigHeader>

  <SettingsBody v-scroll-fade>
    <form :id="formId" @submit.prevent="save">
      <div class="divide-y divide-outline-gray-1">
        <div class="py-3.5">
          <FormControl
            v-if="!isEdit"
            v-model="label"
            label="Name"
            required
            placeholder="Standard shipping"
            description="Only you see it. It cannot be changed later."
          />
          <template v-else>
            <p class="text-sm text-ink-gray-5">Name</p>
            <p class="mt-1 text-base text-ink-gray-8">{{ rule.label }}</p>
          </template>
        </div>

        <SettingsRow
          v-if="inUse"
          title="Used at checkout"
          description="Checkout charges these bands. To stop, pick another rule for checkout."
        >
          <Badge label="In use" theme="green" />
        </SettingsRow>
        <SettingsRow
          v-else
          title="Use at checkout"
          description="On, and checkout charges these bands instead of the rule it uses now."
        >
          <Switch v-model="useAtCheckout" size="sm" />
        </SettingsRow>

        <div class="flex flex-col gap-1 py-3">
          <p class="text-base font-medium text-ink-gray-8">Bands</p>

          <div class="divide-y divide-outline-gray-1">
            <div v-for="row in rows" :key="row.key">
              <button
                type="button"
                class="flex w-full items-center gap-3 py-2.5 text-left disabled:cursor-default"
                :disabled="Boolean(draft) && draft.key !== row.key"
                :aria-expanded="draft?.key === row.key"
                :aria-controls="`band-${row.key}`"
                @click="draft?.key === row.key ? cancelDraft() : editRow(row)"
              >
                <span class="flex min-w-0 flex-1 flex-col">
                  <span class="text-base font-medium text-ink-gray-8 tabular-nums">{{ formatBandRange(shown(row)) }}</span>
                  <span class="truncate text-p-sm text-ink-gray-5">{{ optionLabel(shown(row)) }}</span>
                </span>
                <Badge v-if="shown(row).free_shipping" label="Free" theme="green" />
                <span v-else class="text-base font-medium text-ink-gray-8 tabular-nums">{{ chargeText(shown(row)) }}</span>
                <span
                  class="lucide-chevron-down size-4 shrink-0 text-ink-gray-5 transition-transform"
                  :class="draft?.key === row.key ? 'rotate-180' : ''"
                  aria-hidden="true"
                />
              </button>

              <div
                v-if="draft?.key === row.key"
                :id="`band-${row.key}`"
                class="flex flex-col gap-3 pb-3"
              >
                <div class="flex items-start gap-2">
                  <div class="grid min-w-0 flex-1 grid-cols-2 gap-2">
                    <TextInput
                      v-model="draft.from_value"
                      type="text"
                      inputmode="decimal"
                      label="From"
                    >
                      <template #prefix>
                        <span class="text-ink-gray-5">{{ moneyPrefix }}</span>
                      </template>
                    </TextInput>
                    <TextInput
                      v-model="draft.to_value"
                      type="text"
                      inputmode="decimal"
                      label="To"
                      placeholder="No limit"
                    >
                      <template #prefix>
                        <span class="text-ink-gray-5">{{ moneyPrefix }}</span>
                      </template>
                    </TextInput>
                  </div>
                  <Button
                    icon="lucide-trash-2"
                    variant="ghost"
                    aria-label="Remove band"
                    @click="removeRow(row.key)"
                  />
                </div>

                <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <div class="flex flex-col gap-1.5">
                    <span class="text-xs text-ink-gray-5">Charge</span>
                    <div class="flex items-center gap-2">
                      <TabButtons v-model="draft.charge" :options="CHARGE_KINDS" />
                      <TextInput
                        v-if="draft.charge === 'amount'"
                        v-model="draft.shipping_amount"
                        class="min-w-0 flex-1"
                        type="text"
                        inputmode="decimal"
                        aria-label="Charge"
                      >
                        <template #prefix>
                          <span class="text-ink-gray-5">{{ moneyPrefix }}</span>
                        </template>
                      </TextInput>
                    </div>
                  </div>
                  <div class="flex flex-col gap-1.5">
                    <span class="text-xs text-ink-gray-5">Delivery option</span>
                    <Select v-model="draft.shipping_service" :options="optionChoices" aria-label="Delivery option" />
                  </div>
                </div>

                <p
                  v-for="message in draftConflicts"
                  :key="message"
                  class="flex items-start gap-1.5 text-p-sm text-ink-red-6"
                  role="alert"
                >
                  <span class="lucide-circle-alert mt-0.5 size-4 shrink-0" aria-hidden="true" />
                  {{ message }}
                </p>

                <div class="flex items-center justify-end gap-2">
                  <Button label="Cancel" @click="cancelDraft" />
                  <Button
                    label="Save"
                    variant="solid"
                    theme="gray"
                    :disabled="draftConflicts.length > 0"
                    @click="applyDraft"
                  />
                </div>
              </div>
            </div>
          </div>

          <p v-if="!rows.length" class="py-2 text-p-sm text-ink-gray-5">
            No bands yet. Add one for each range of order totals you charge differently.
          </p>

          <div class="pt-1">
            <Button
              label="Add band"
              icon-left="lucide-plus"
              variant="subtle"
              theme="gray"
              :disabled="Boolean(draft)"
              @click="addRow"
            />
          </div>

          <p
            v-if="serverError"
            class="flex items-start gap-1.5 text-p-sm text-ink-red-6"
            role="alert"
          >
            <span class="lucide-circle-alert mt-0.5 size-4 shrink-0" aria-hidden="true" />
            {{ serverError }}
          </p>
        </div>
      </div>
    </form>
  </SettingsBody>
</template>
