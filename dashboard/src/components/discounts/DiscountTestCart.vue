<script setup>
import { computed, ref } from 'vue'
import { Button, Select } from 'frappe-ui'
import { watchDebounced } from '@vueuse/core'
import TestCartPicker from './TestCartPicker.vue'
import { useAdminAction, wasAborted } from '../../data/api'
import { errorMessage } from '../../data/errors'
import { discountMoney, moneyIn } from '../../data/format'

const props = defineProps({ discount: { type: Object, required: true } })

let nextLineId = 1
const newLine = () => ({ id: nextLineId++, item_code: null, qty: 1 })

const lines = ref([newLine()])
const paymentKind = ref('prepaid')
const shopper = ref('returning')
const customer = ref(null)
const result = ref(null)

const preview = useAdminAction('discounts.test_discount', { quiet: true })
const refusal = computed(() => (preview.error && !wasAborted(preview.error) ? errorMessage(preview.error) : null))

const money = (value) => moneyIn(value, result.value?.currency)

const QUANTITIES = [1, 2, 3, 4, 5].map((qty) => ({ label: String(qty), value: qty }))

watchDebounced(
  () => [props.discount, lines.value, paymentKind.value, shopper.value, customer.value],
  async () => {
    const chosen = lines.value.filter((line) => line.item_code).map(({ item_code, qty }) => ({ item_code, qty }))
    if (!chosen.length) {
      result.value = null
      return
    }
    try {
      result.value = await preview.submit({
        discount: props.discount,
        lines: chosen,
        payment_kind: paymentKind.value,
        first_order: shopper.value === 'new' ? 1 : 0,
        customer: customer.value,
      })
    } catch {
      if (refusal.value) result.value = null
    }
  },
  { debounce: 400, deep: true, immediate: true },
)
</script>

<template>
  <section class="rounded-5 border border-outline-gray-1 p-4">
    <h2 class="text-base-semibold text-ink-gray-8">{{ __('Test a cart') }}</h2>
    <p class="mt-0.5 text-p-sm text-ink-gray-5">{{ __('Priced the way checkout prices it, with this draft.') }}</p>

    <div class="mt-3 space-y-2">
      <!-- min-w-0: else a long name pushes the remove button out. -->
      <div v-for="(line, index) in lines" :key="line.id" class="grid grid-cols-[minmax(0,1fr)_4rem_auto] gap-1.5">
        <TestCartPicker
          v-model="line.item_code"
          class="min-w-0"
          target-type="Item"
          :placeholder="__('Search items')"
          :aria-label="__('Item on line {0}', [index + 1])"
        />
        <Select v-model="line.qty" :options="QUANTITIES" :aria-label="__('Quantity on line {0}', [index + 1])" />
        <Button icon="lucide-x" variant="ghost" :aria-label="__('Remove line {0}', [index + 1])" @click="lines.splice(index, 1)" />
      </div>
      <Button :label="__('Add item')" icon-left="lucide-plus" size="sm" @click="lines.push(newLine())" />
    </div>

    <div class="mt-3 grid grid-cols-[minmax(0,1fr)_auto] gap-1.5">
      <TestCartPicker v-model="customer" class="min-w-0" target-type="Customer" :placeholder="__('Any customer')" :aria-label="__('Customer')" />
      <Button v-if="customer" icon="lucide-x" variant="ghost" :aria-label="__('Clear customer')" @click="customer = null" />
    </div>

    <div class="mt-2 grid gap-2" :class="customer ? 'grid-cols-1' : 'grid-cols-2'">
      <Select
        v-model="paymentKind"
        :aria-label="__('Payment')"
        :options="[{ label: __('Prepaid'), value: 'prepaid' }, { label: __('Cash on delivery'), value: 'cod' }]"
      />
      <Select
        v-if="!customer"
        v-model="shopper"
        :aria-label="__('Shopper')"
        :options="[{ label: __('Returning shopper'), value: 'returning' }, { label: __('New shopper'), value: 'new' }]"
      />
    </div>

    <p v-if="refusal" class="mt-4 flex items-start gap-1.5 border-t border-outline-gray-1 pt-3 text-p-sm text-ink-red-6">
      <span class="lucide-circle-alert mt-0.5 size-3.5 shrink-0" aria-hidden="true" />{{ refusal }}
    </p>
    <template v-else-if="result">
      <dl class="mt-4 space-y-1.5 border-t border-outline-gray-1 pt-3 text-p-sm">
        <div class="flex justify-between text-ink-gray-7"><dt>{{ __('Subtotal') }}</dt><dd class="tabular-nums">{{ money(result.subtotal) }}</dd></div>
        <div class="flex justify-between text-ink-gray-7">
          <dt>{{ __('Discount') }}</dt>
          <dd class="tabular-nums" :class="{ 'font-medium text-ink-gray-8': result.discount }">{{ discountMoney(result.discount, money) }}</dd>
        </div>
        <div class="flex justify-between text-base-medium text-ink-gray-8"><dt>{{ __('Total') }}</dt><dd class="tabular-nums">{{ money(result.total) }}</dd></div>
      </dl>
      <p v-for="reason in result.reasons" :key="reason" class="mt-2 flex items-center gap-1.5 text-p-sm text-ink-amber-7">
        <span class="lucide-circle-alert size-3.5 shrink-0" aria-hidden="true" />{{ reason }}
      </p>
    </template>
  </section>
</template>
