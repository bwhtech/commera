<script setup>
/**
 * Take stock in against any mix of a product's sizes in one pass.
 *
 * Quantities are ADDED, never set: commera's only stock write is
 * `Style Attribute Variant.receive_stock`, a submitted Material Receipt into the
 * ecommerce warehouse. A valuation rate is optional per line — left blank, the
 * item's own valuation stands.
 */
import { computed, reactive, watch } from 'vue'
import { Button, Dialog, TextInput, toast } from 'frappe-ui'
import { useAdminAction } from '../../data/api'

const props = defineProps({
  // The rows ProductStock already builds: { id, title, sku, onHand }.
  rows: { type: Array, required: true },
})

const open = defineModel('open', { type: Boolean, required: true })
const emit = defineEmits(['received'])

const receiveAction = useAdminAction('inventory.receive_stock')

const drafts = reactive({})

// Reset on every open rather than on mount: a dialog left half-filled and dismissed
// must not come back carrying the abandoned numbers.
watch(open, (isOpen) => {
  if (!isOpen) return
  for (const key of Object.keys(drafts)) delete drafts[key]
  for (const row of props.rows) drafts[row.id] = { qty: '', rate: '' }
})

const lines = computed(() =>
  props.rows
    .filter((row) => Number(drafts[row.id]?.qty) > 0)
    .map((row) => ({ itemCode: row.id, qty: Number(drafts[row.id].qty), rate: drafts[row.id].rate })),
)

const totalQty = computed(() => lines.value.reduce((sum, line) => sum + line.qty, 0))

async function receive() {
  const received_quantities = Object.fromEntries(lines.value.map((line) => [line.itemCode, line.qty]))
  const valuation_rates = Object.fromEntries(
    lines.value.filter((line) => line.rate !== '' && line.rate != null).map((line) => [line.itemCode, Number(line.rate)]),
  )

  let result
  try {
    result = await receiveAction.submit({ received_quantities, valuation_rates })
  } catch {
    return
  }
  if (!result) return

  open.value = false
  const count = result.stock_entries?.length ?? 0
  toast.success(`Received ${totalQty.value} across ${lines.value.length} sizes`, {
    description: `${count} Material Receipt${count === 1 ? '' : 's'} submitted.`,
  })
  emit('received')
}
</script>

<template>
  <Dialog v-model:open="open" title="Receive stock" size="xl">
    <template #default>
      <p class="text-p-sm text-ink-gray-5">
        Quantities are added to what is on hand, as a Material Receipt into the shop's warehouse.
        Leave the valuation rate blank to keep the item's own.
      </p>

      <div class="mt-4 space-y-3">
        <div
          v-for="row in rows"
          :key="row.id"
          class="flex flex-col gap-2 border-b border-outline-gray-1 pb-3 last:border-0 sm:flex-row sm:items-center sm:gap-3"
        >
          <div class="min-w-0 flex-1">
            <p class="truncate text-base text-ink-gray-8">{{ row.title }}</p>
            <p class="truncate text-sm text-ink-gray-5">{{ row.sku }} · {{ row.onHand }} on hand</p>
          </div>
          <TextInput
            v-model="drafts[row.id].qty"
            type="number"
            size="sm"
            class="w-full sm:w-28"
            placeholder="Qty"
          />
          <TextInput
            v-model="drafts[row.id].rate"
            type="number"
            size="sm"
            class="w-full sm:w-36"
            placeholder="Valuation rate"
          />
        </div>
      </div>
    </template>

    <template #actions>
      <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button
          class="w-full sm:w-auto"
          label="Cancel"
          :disabled="receiveAction.loading"
          @click="open = false"
        />
        <Button
          class="w-full sm:w-auto"
          variant="solid"
          theme="gray"
          :label="totalQty ? `Receive ${totalQty}` : 'Receive stock'"
          :loading="receiveAction.loading"
          :disabled="!lines.length || receiveAction.loading"
          @click="receive"
        />
      </div>
    </template>
  </Dialog>
</template>
