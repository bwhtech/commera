<script setup>
import { ref } from 'vue'
import { Button, Dialog, toast } from 'frappe-ui'
import { useMethodAction } from '../data/api'
import { money } from '../data/format'

const props = defineProps({
  orderId: { type: String, required: true },
  // The dict from commera.api.orders.get_sales_order_refund_status. Only
  // `can_refund` is guaranteed; every other key is read defensively.
  status: { type: Object, default: () => ({}) },
})

const open = defineModel('open', { type: Boolean, required: true })
const emit = defineEmits(['refunded'])

const refundAction = useMethodAction('commera.api.orders.create_refund_payment_entry')

// Money leaves the shop on this click, so the button is held down by our own flag
// rather than by the request's loading state alone: a second press must never
// reach the server, even in the gap before the first one is in flight.
const refunding = ref(false)

async function refund() {
  if (refunding.value) return
  refunding.value = true
  try {
    // No `amount`: the server refunds everything it still considers refundable,
    // and it is the one that clamps. It throws on failure — useMethodAction has
    // already surfaced the thrown message verbatim as a toast.
    let paymentEntry
    try {
      paymentEntry = await refundAction.submit({ order_id: props.orderId })
    } catch {
      return
    }
    if (!paymentEntry) return

    open.value = false
    toast.success(`Refunded ${money(props.status.refundable_amount)}`, {
      description: `Payment Entry ${paymentEntry} created.`,
    })
    emit('refunded')
  } finally {
    refunding.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open" title="Refund this order" size="sm" :dismissible="!refunding">
    <template #default>
      <div class="space-y-3">
        <p class="text-p-base text-ink-gray-7">
          {{ money(status.refundable_amount) }} goes back to the customer on {{ orderId }}, the same
          way they paid. This cannot be undone from here.
        </p>

        <p v-if="status.amount_refunded" class="text-p-sm text-ink-gray-5">
          {{ money(status.amount_refunded) }} has already been refunded on this order.
        </p>

        <p v-if="status.only_charges" class="text-p-sm text-ink-gray-5">
          The goods are already fully refunded — only shipping and other charges are left.
        </p>
      </div>
    </template>

    <template #actions>
      <!-- Stacked on a phone, side by side from sm up; the money-moving button is
           never the one under a stray thumb at the top. -->
      <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button class="w-full sm:w-auto" label="Keep the payment" :disabled="refunding" @click="open = false" />
        <Button
          class="w-full sm:w-auto"
          variant="solid"
          theme="red"
          :label="`Refund ${money(status.refundable_amount)}`"
          :loading="refunding"
          :disabled="refunding"
          @click="refund"
        />
      </div>
    </template>
  </Dialog>
</template>
