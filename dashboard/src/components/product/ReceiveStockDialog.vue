<script setup>
/**
 * Add stock to any mix of a product's sizes in one pass.
 *
 * Quantities are ADDED, never set: commera's only stock write is
 * `Style Attribute Variant.receive_stock`, a submitted Material Receipt into the
 * ecommerce warehouse. The cost per item is optional per line — left blank, the
 * item's own valuation stands.
 */
import { computed, reactive, watch } from 'vue'
import { FormControl, toast } from 'frappe-ui'
import FormDialog from '../FormDialog.vue'
import { useAdminAction, trySubmit } from '../../data/api'
import { symbolFor } from '../../data/format'
import { __ } from '../../data/translation'
import { useIsMobile } from '../../utils/useIsMobile'

const props = defineProps({
  // { id: item code, title: what the seller calls it ("Black · M"), onHand }.
  rows: { type: Array, required: true },
})

const open = defineModel('open', { type: Boolean, required: true })
const emit = defineEmits(['received'])

const receiveAction = useAdminAction('inventory.receive_stock')
const currencySymbol = symbolFor()

// Side by side, several rows share one header instead of repeating both labels on every row;
// stacked on a phone, each row keeps its own.
const isMobile = useIsMobile()
const labelEachRow = computed(() => isMobile.value || props.rows.length === 1)

const drafts = reactive({})

// Reset on every open rather than on mount: a dialog left half-filled and dismissed
// must not come back carrying the abandoned numbers.
watch(
  open,
  (isOpen) => {
    if (!isOpen) return
    for (const key of Object.keys(drafts)) delete drafts[key]
    for (const row of props.rows) drafts[row.id] = { qty: '', rate: '' }
  },
  { immediate: true },
)

const lines = computed(() =>
  props.rows
    .filter((row) => Number(drafts[row.id]?.qty) > 0)
    .map((row) => ({ itemCode: row.id, qty: Number(drafts[row.id].qty), rate: drafts[row.id].rate })),
)

const totalQty = computed(() => lines.value.reduce((sum, line) => sum + line.qty, 0))

const resultingStock = (row) => (row.onHand ?? 0) + Math.max(0, Number(drafts[row.id]?.qty) || 0)

async function receive() {
  if (!lines.value.length || receiveAction.loading) return
  const received_quantities = Object.fromEntries(lines.value.map((line) => [line.itemCode, line.qty]))
  const valuation_rates = Object.fromEntries(
    lines.value.filter((line) => line.rate !== '' && line.rate != null).map((line) => [line.itemCode, Number(line.rate)]),
  )

  const received = await trySubmit(receiveAction, { received_quantities, valuation_rates })
  if (!received) return

  open.value = false
  toast.success(__('Stock added'), {
    description:
      lines.value.length === 1
        ? __('Added {0}.', [totalQty.value])
        : __('Added {0} across {1} sizes.', [totalQty.value, lines.value.length]),
  })
  emit('received')
}
</script>

<template>
  <FormDialog
    v-model:open="open"
    :title="__('Add stock')"
    :primary-label="__('Add stock')"
    :primary-disabled="!lines.length"
    :reason="lines.length ? '' : __('Enter a quantity to add.')"
    :loading="receiveAction.loading"
    @submit="receive"
  >
    <p class="text-p-sm text-ink-gray-5">{{ __('Adds to what you already have.') }}</p>

    <div v-if="!labelEachRow" class="mt-4 flex gap-3 border-b border-outline-gray-1 pb-1.5 text-sm text-ink-gray-5">
      <span class="flex-1">{{ __('Variant') }}</span>
      <span class="w-28">{{ __('Quantity to add') }}</span>
      <span class="w-40">{{ __('Cost per item (optional)') }}</span>
    </div>
    <div class="divide-y divide-outline-gray-1" :class="labelEachRow ? 'mt-4' : 'mt-3'">
      <div
        v-for="row in rows"
        :key="row.id"
        class="grid grid-cols-2 gap-3 py-3 first:pt-0 last:pb-0 sm:flex sm:items-end"
      >
        <div class="col-span-2 min-w-0 sm:flex-1" :class="{ 'sm:pb-1.5': labelEachRow }">
          <p class="truncate text-base text-ink-gray-8">{{ row.title }}</p>
          <p class="mt-0.5 text-sm text-ink-gray-5 tabular-nums">
            {{
              Number(drafts[row.id]?.qty) > 0
                ? __('{0} in stock → {1}', [row.onHand ?? 0, resultingStock(row)])
                : __('{0} in stock', [row.onHand ?? 0])
            }}
          </p>
        </div>
        <FormControl
          v-model="drafts[row.id].qty"
          class="sm:w-28"
          type="number"
          inputmode="numeric"
          min="0"
          :label="labelEachRow ? __('Quantity to add') : ''"
          :aria-label="__('Quantity to add for {0}', [row.title])"
        />
        <FormControl
          v-model="drafts[row.id].rate"
          class="sm:w-40"
          type="number"
          inputmode="decimal"
          min="0"
          :label="labelEachRow ? __('Cost per item (optional)') : ''"
          :aria-label="__('Cost per item for {0}', [row.title])"
        >
          <template #prefix>
            <span class="text-base text-ink-gray-5">{{ currencySymbol }}</span>
          </template>
        </FormControl>
      </div>
    </div>
  </FormDialog>
</template>
