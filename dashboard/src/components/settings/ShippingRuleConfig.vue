<script setup>
import { computed, ref, useId } from 'vue'
import {
  Badge,
  Button,
  Combobox,
  FormControl,
  SettingsBody,
  SettingsRow,
  Switch,
  TextInput,
  toast,
} from 'frappe-ui'
import SettingsConfigHeader from './SettingsConfigHeader.vue'
import { errorMessage } from '../../data/errors'
import { exactMoney, symbolFor } from '../../data/format'
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

// The submit button sits outside the form, so `form` is what runs the name's `required`.
const formId = useId()

const isEdit = computed(() => Boolean(props.rule))
const moneyUnit = symbolFor(props.currency || undefined)

// '' is the "Any option" row: a band that names no delivery option.
const optionChoices = computed(() => [
  { label: 'Any option', value: '' },
  ...props.deliveryOptions.map((option) => ({
    label: option.title,
    value: option.name,
    description: option.enabled ? undefined : 'Off at checkout',
  })),
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
    shipping_service: row.shipping_service,
  }
}

function fromDraft(band) {
  return {
    key: band.key,
    from_value: Number(band.from_value) || 0,
    to_value: Number(band.to_value) || 0,
    shipping_amount: Number(band.shipping_amount) || 0,
    free_shipping: !(Number(band.shipping_amount) > 0),
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

function bandSentence(row) {
  const price = row.free_shipping ? 'delivery is free' : `${exactMoney(row.shipping_amount)} is charged`
  const from = exactMoney(row.from_value)
  const to = exactMoney(row.to_value)

  if (!row.from_value && !row.to_value) return `For every order, ${price}`
  if (!row.to_value) return `For orders ${from} and above, ${price}`
  return `For orders ${from} to ${to}, ${price}`
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
              <div class="flex items-center gap-3 py-2.5">
                <div class="flex min-w-0 flex-1 flex-col">
                  <span class="text-base text-ink-gray-8 tabular-nums">{{ bandSentence(shown(row)) }}</span>
                  <span class="truncate text-p-sm text-ink-gray-5">{{ optionLabel(shown(row)) }}</span>
                </div>
                <Button
                  v-if="draft?.key !== row.key"
                  label="Edit"
                  :disabled="Boolean(draft)"
                  @click="editRow(row)"
                />
              </div>

              <div
                v-if="draft?.key === row.key"
                :id="`band-${row.key}`"
                class="flex flex-col gap-4 pb-4"
              >
                <div class="grid grid-cols-1 gap-x-2 gap-y-4 sm:grid-cols-2">
                  <TextInput
                    v-model="draft.from_value"
                    type="text"
                    inputmode="decimal"
                    :label="`From (${moneyUnit})`"
                  />
                  <TextInput
                    v-model="draft.to_value"
                    type="text"
                    inputmode="decimal"
                    :label="`To (${moneyUnit})`"
                    placeholder="No limit"
                  />
                  <TextInput
                    v-model="draft.shipping_amount"
                    type="text"
                    inputmode="decimal"
                    :label="`Charge (${moneyUnit})`"
                    placeholder="0 for free delivery"
                  />
                  <Combobox
                    v-model="draft.shipping_service"
                    trigger="button"
                    label="Delivery option"
                    placeholder="Search delivery options"
                    :options="optionChoices"
                  />
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

                <div class="flex items-center gap-2 pt-2">
                  <Button
                    label="Remove band"
                    icon-left="lucide-trash-2"
                    variant="ghost"
                    theme="red"
                    @click="removeRow(row.key)"
                  />
                  <Button class="ml-auto" label="Cancel" @click="cancelDraft" />
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
