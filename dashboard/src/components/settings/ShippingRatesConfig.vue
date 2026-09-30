<script setup>
import { computed, ref } from 'vue'
import { Button, Checkbox, SettingsBody, TextInput, toast } from 'frappe-ui'
import SettingsConfigHeader from './SettingsConfigHeader.vue'
import { errorMessage } from '../../data/errors'
import { findBandConflicts, formatBandRange } from '../../data/shippingRates'

const props = defineProps({
  title: { type: String, required: true },
  // Null edits the bands that name no delivery option.
  shippingService: { type: String, default: null },
  bands: { type: Array, default: () => [] },
  // Every other band on the rule: ERPNext refuses an overlap across the whole rule.
  otherBands: { type: Array, default: () => [] },
  optionTitles: { type: Object, default: () => ({}) },
  boundaryUnit: { type: String, required: true },
  currency: { type: String, default: '' },
  formatBoundary: { type: Function, required: true },
  submit: { type: Function, required: true },
})

const emit = defineEmits(['back'])

// The From and To boxes need room for a five-digit value; below that 1fr collapses to nothing.
const GRID = 'grid grid-cols-[minmax(4.5rem,1fr)_minmax(4.5rem,1fr)_minmax(5rem,1fr)_auto_auto] items-center gap-2'

let nextKey = 0
const toRow = (band) => ({
  key: nextKey++,
  draft: true,
  from_value: band.from_value ?? 0,
  // A stored 0 means "and above", which reads as an empty box, not as a limit of zero.
  to_value: Number(band.to_value) ? band.to_value : '',
  shipping_amount: band.shipping_amount ?? 0,
  free_shipping: Boolean(band.free_shipping),
})

const rows = ref(props.bands.map(toRow))
const saving = ref(false)
const serverError = ref('')

function addRow() {
  const highestTo = Math.max(0, ...rows.value.map((row) => Number(row.to_value) || 0))
  rows.value.push(toRow({ from_value: highestTo, to_value: 0, shipping_amount: 0 }))
}

function removeRow(key) {
  rows.value = rows.value.filter((row) => row.key !== key)
}

function ownerOf(band) {
  if (!band.shipping_service) return 'an untied band'
  return props.optionTitles[band.shipping_service] ?? band.shipping_service
}

function describeConflict({ kind, bands }) {
  const others = bands.filter((band) => !band.draft)
  if (kind === 'order') return 'Each band has to start below where it ends.'
  if (kind === 'open') {
    return others.length
      ? `Only one band can be left open-ended, and ${ownerOf(others[0])} already has it.`
      : 'Only one band can be left open-ended.'
  }
  if (others.length) {
    return `${formatBandRange(others[0], props.formatBoundary)} is already ${ownerOf(others[0])}'s. Ranges can't overlap.`
  }
  return `${bands.map((band) => formatBandRange(band, props.formatBoundary)).join(' and ')} overlap.`
}

const conflictMessages = computed(() => {
  const conflicts = findBandConflicts([...rows.value, ...props.otherBands]).filter((conflict) =>
    conflict.bands.some((band) => band.draft),
  )
  return [...new Set(conflicts.map(describeConflict))]
})

async function save() {
  saving.value = true
  serverError.value = ''
  try {
    const { data, error } = await props.submit(
      rows.value.map((row) => ({
        from_value: Number(row.from_value) || 0,
        to_value: Number(row.to_value) || 0,
        shipping_amount: row.free_shipping ? 0 : Number(row.shipping_amount) || 0,
        free_shipping: row.free_shipping ? 1 : 0,
      })),
    )
    if (!data) {
      serverError.value = errorMessage(error)
      return
    }

    toast.success(`${props.title} rates saved`)
    emit('back')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <SettingsConfigHeader
    :title="title"
    description="Checkout charges the band the order falls in. Leave To blank for “and above”."
    @back="emit('back')"
  >
    <template #actions>
      <Button
        variant="solid"
        theme="gray"
        label="Save"
        :loading="saving"
        :disabled="conflictMessages.length > 0"
        @click="save"
      />
    </template>
  </SettingsConfigHeader>

  <SettingsBody v-scroll-fade>
    <div class="flex flex-col gap-2 py-3">
      <div v-if="rows.length" :class="GRID" class="text-sm text-ink-gray-5">
        <span>From ({{ boundaryUnit }})</span>
        <span>To ({{ boundaryUnit }})</span>
        <span>Charge{{ currency ? ` (${currency})` : '' }}</span>
        <span class="sr-only">Free</span>
        <span class="sr-only">Remove</span>
      </div>

      <div v-for="(row, index) in rows" :key="row.key" :class="GRID">
        <TextInput
          v-model="row.from_value"
          type="number"
          min="0"
          :aria-label="`Band ${index + 1} from`"
        />
        <TextInput
          v-model="row.to_value"
          type="number"
          min="0"
          placeholder="and above"
          :aria-label="`Band ${index + 1} to`"
        />
        <TextInput
          v-model="row.shipping_amount"
          type="number"
          min="0"
          :disabled="row.free_shipping"
          :aria-label="`Band ${index + 1} charge`"
        />
        <Checkbox v-model="row.free_shipping" label="Free" />
        <Button
          icon="lucide-x"
          variant="ghost"
          :aria-label="`Remove band ${index + 1}`"
          @click="removeRow(row.key)"
        />
      </div>

      <p v-if="!rows.length" class="text-p-sm text-ink-gray-5">
        No bands yet. Add one for each range of orders you charge differently.
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
  </SettingsBody>
</template>
