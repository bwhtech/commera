<script setup>
/**
 * Take stock in against any mix of a product's sizes in one pass.
 *
 * Quantities are ADDED, never set: commera's only stock write is
 * `Style Attribute Variant.receive_stock`.
 */
import { computed, reactive, watch } from 'vue'
import { Button, Dialog, TextInput, toast } from 'frappe-ui'
import { useAdminAction, trySubmit } from '../../data/api'
import { __ } from '../../data/translation'

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
  for (const row of props.rows) drafts[row.id] = { qty: '' }
})

const lines = computed(() =>
  props.rows
    .filter((row) => Number(drafts[row.id]?.qty) > 0)
    .map((row) => ({ itemCode: row.id, qty: Number(drafts[row.id].qty) })),
)

const totalQty = computed(() => lines.value.reduce((sum, line) => sum + line.qty, 0))

async function receive() {
  const received_quantities = Object.fromEntries(lines.value.map((line) => [line.itemCode, line.qty]))

  const received = await trySubmit(receiveAction, { received_quantities })
  if (!received) return

  open.value = false
  const count = lines.value.length
  toast.success(count === 1 ? __('Stock added') : __('Stock added to {0} sizes', [count]))
  emit('received')
}
</script>

<template>
  <Dialog v-model:open="open" :title="__('Add stock')" size="xl">
    <template #default>
      <div class="space-y-3">
        <div
          v-for="row in rows"
          :key="row.id"
          class="flex flex-col gap-2 border-b border-outline-gray-1 pb-3 last:border-0 sm:flex-row sm:items-center sm:gap-3"
        >
          <div class="min-w-0 flex-1">
            <p class="truncate text-base text-ink-gray-8">{{ row.title }}</p>
            <p class="truncate text-sm text-ink-gray-5">{{ row.sku }} · {{ __('{0} on hand', [row.onHand]) }}</p>
          </div>
          <TextInput
            v-model="drafts[row.id].qty"
            type="number"
            size="sm"
            class="w-full sm:w-28"
            :placeholder="__('Qty')"
          />
        </div>
      </div>
    </template>

    <template #actions>
      <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button
          class="w-full sm:w-auto"
          :label="__('Cancel')"
          :disabled="receiveAction.loading"
          @click="open = false"
        />
        <Button
          class="w-full sm:w-auto"
          variant="solid"
          theme="gray"
          :label="totalQty ? __('Add {0}', [totalQty]) : __('Add stock')"
          :loading="receiveAction.loading"
          :disabled="!lines.length || receiveAction.loading"
          @click="receive"
        />
      </div>
    </template>
  </Dialog>
</template>
