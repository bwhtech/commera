<script setup>
/**
 * Creating or editing one shipping rate: the price bands a delivery option charges from.
 *
 * Bands are read lowest first and the first one covering the cart wins, and a cart outside
 * every band gets no price from this rule at all — it falls through to the carrier's rate
 * or the option's fallback. So "free above X" is not a setting; it is an open-ended top
 * band that charges nothing, and the shortcut below writes exactly that band.
 */
import { computed, ref, useId, watch } from 'vue'
import { Button, Dialog, FormControl, TabButtons, TextInput, toast } from 'frappe-ui'
import SettingsLinkControl from './SettingsLinkControl.vue'

const props = defineProps({
  // Null while creating; the rule being edited otherwise.
  rule: { type: Object, default: null },
  defaultAccount: { type: String, default: '' },
  linkOptionsPath: { type: String, default: '' },
  submit: { type: Function, required: true },
})

const emit = defineEmits(['saved'])

const open = defineModel('open', { type: Boolean, required: true })

const BASED_ON_OPTIONS = [
  { label: 'Cart value', value: 'Net Total' },
  { label: 'Weight', value: 'Net Weight' },
]

const ACCOUNT_FIELD = { fieldname: 'account', options: 'Account' }

const formId = useId()

const label = ref('')
const basedOn = ref('Net Total')
const account = ref('')
const bands = ref([])
const saving = ref(false)

const isEdit = computed(() => Boolean(props.rule))
const byWeight = computed(() => basedOn.value === 'Net Weight')

// An open top band already answers "everything above", so a second one would be refused.
const hasOpenBand = computed(() => bands.value.some((band) => !Number(band.to_value)))

function blankBand(fromValue = 0) {
  return { from_value: fromValue, to_value: '', shipping_amount: '' }
}

// Reset on open: the dialog stays mounted, so a second rule would inherit the first's bands.
watch(open, (isOpen) => {
  if (!isOpen) return

  label.value = props.rule?.label ?? ''
  basedOn.value = props.rule?.calculate_based_on === 'Net Weight' ? 'Net Weight' : 'Net Total'
  account.value = props.rule?.account ?? props.defaultAccount
  bands.value = props.rule?.bands?.length
    ? props.rule.bands.map((band) => ({ ...band, to_value: band.to_value || '' }))
    : [blankBand()]
})

function highestTo() {
  return Math.max(0, ...bands.value.map((band) => Number(band.to_value) || 0))
}

// A new band starts where the last one stopped, which is the only place it can go
// without overlapping.
function addBand() {
  bands.value.push(blankBand(highestTo()))
}

function addFreeAbove() {
  bands.value.push({ from_value: highestTo(), to_value: '', shipping_amount: 0 })
}

function removeBand(index) {
  bands.value.splice(index, 1)
}

async function save() {
  saving.value = true
  try {
    const saved = await props.submit({
      name: props.rule?.name ?? '',
      label: label.value.trim(),
      calculate_based_on: basedOn.value,
      account: account.value,
      bands: bands.value.map((band) => ({
        from_value: Number(band.from_value) || 0,
        to_value: Number(band.to_value) || 0,
        shipping_amount: Number(band.shipping_amount) || 0,
      })),
    })
    if (!saved) return

    open.value = false
    toast.success(isEdit.value ? 'Shipping rate saved' : 'Shipping rate added')
    emit('saved', label.value.trim())
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog
    v-model:open="open"
    size="2xl"
    :title="isEdit ? `Edit ${rule.label}` : 'Add a shipping rate'"
  >
    <template #default>
      <form :id="formId" class="flex flex-col gap-5" @submit.prevent="save">
        <FormControl
          v-if="!isEdit"
          v-model="label"
          label="Name"
          required
          placeholder="Standard rates"
          description="Delivery options pick a rate by this name, so it cannot be changed later."
        />

        <div class="flex flex-col gap-1.5">
          <span class="text-xs text-ink-gray-5">Price by</span>
          <TabButtons v-model="basedOn" :options="BASED_ON_OPTIONS" />
        </div>

        <div class="flex flex-col gap-2">
          <div class="grid grid-cols-[1fr_1fr_1fr_auto] gap-2 text-xs text-ink-gray-5">
            <span>{{ byWeight ? 'From weight' : 'From cart value' }}</span>
            <span>{{ byWeight ? 'To weight' : 'To cart value' }}</span>
            <span>Charge</span>
            <span class="w-7" aria-hidden="true" />
          </div>

          <div
            v-for="(band, index) in bands"
            :key="index"
            class="grid grid-cols-[1fr_1fr_1fr_auto] items-center gap-2"
          >
            <TextInput v-model="band.from_value" type="number" min="0" step="any" required />
            <TextInput
              v-model="band.to_value"
              type="number"
              min="0"
              step="any"
              placeholder="and above"
            />
            <TextInput
              v-model="band.shipping_amount"
              type="number"
              min="0"
              step="any"
              placeholder="0 = Free"
              required
            />
            <Button
              icon="lucide-x"
              variant="ghost"
              :disabled="bands.length === 1"
              :aria-label="`Remove band ${index + 1}`"
              @click="removeBand(index)"
            />
          </div>

          <div class="flex flex-wrap gap-2">
            <Button label="Add band" icon-left="lucide-plus" @click="addBand" />
            <Button
              label="Free above"
              icon-left="lucide-gift"
              :disabled="hasOpenBand"
              @click="addFreeAbove"
            />
          </div>

          <p class="text-p-sm text-ink-gray-5">
            Leave “To” blank on the top band to cover everything above it. A cart no band
            covers is priced by the carrier or the option's fallback instead.
          </p>
        </div>

        <div class="flex flex-col gap-1.5">
          <span class="text-xs text-ink-gray-5">Post charges to</span>
          <SettingsLinkControl
            v-if="linkOptionsPath"
            v-model="account"
            :field="ACCOUNT_FIELD"
            :options-path="linkOptionsPath"
          />
          <p v-if="!account" class="text-p-sm text-ink-gray-5">
            No freight account was found for your company. Pick the expense account shipping
            charges should be booked against.
          </p>
        </div>
      </form>
    </template>

    <template #actions>
      <Button
        class="w-full"
        type="submit"
        :form="formId"
        variant="solid"
        theme="gray"
        :loading="saving"
        :label="isEdit ? 'Save' : 'Add'"
      />
    </template>
  </Dialog>
</template>
