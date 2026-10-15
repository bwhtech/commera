<script setup>
import { ref, watch } from 'vue'
import { Button, Combobox, Select } from 'frappe-ui'
import { watchDebounced } from '@vueuse/core'
import { money } from '../../data/format'
import { searchTargets, testDiscount } from '../../data/discounts'

const props = defineProps({ discount: { type: Object, required: true } })

const lines = ref([{ item_code: null, qty: 1 }])
const paymentKind = ref('prepaid')
const shopper = ref('returning')
const itemQuery = ref('')
const itemOptions = ref([])
const result = ref(null)

const QUANTITIES = [1, 2, 3, 4, 5].map((qty) => ({ label: String(qty), value: qty }))

watch(
  itemQuery,
  async () => {
    itemOptions.value = (await searchTargets('Item', itemQuery.value, true)) ?? []
  },
  { immediate: true },
)

// Priced on the server with the unsaved draft, the same way checkout prices a cart.
watchDebounced(
  () => [props.discount, lines.value, paymentKind.value, shopper.value],
  async () => {
    const chosen = lines.value.filter((line) => line.item_code)
    result.value = chosen.length ? await testDiscount(props.discount, chosen, paymentKind.value, shopper.value === 'new') : null
  },
  { debounce: 400, deep: true, immediate: true },
)
</script>

<template>
  <section class="rounded-5 border border-outline-gray-1 p-4">
    <h2 class="text-base-semibold text-ink-gray-8">Test a cart</h2>
    <p class="mt-0.5 text-p-sm text-ink-gray-5">Priced the way checkout prices it, with this draft.</p>

    <div class="mt-3 space-y-2">
      <!-- min-w-0 lets a long item name truncate inside its track instead of pushing the
           remove button out of the card. -->
      <div v-for="(line, index) in lines" :key="index" class="grid grid-cols-[minmax(0,1fr)_4rem_auto] gap-1.5">
        <Combobox
          v-model="line.item_code"
          v-model:query="itemQuery"
          class="min-w-0"
          :options="itemOptions"
          :filterable="false"
          placeholder="Search items"
        />
        <Select v-model="line.qty" :options="QUANTITIES" />
        <Button icon="lucide-x" variant="ghost" :aria-label="`Remove line ${index + 1}`" @click="lines.splice(index, 1)" />
      </div>
      <Button label="Add item" icon-left="lucide-plus" size="sm" @click="lines.push({ item_code: null, qty: 1 })" />
    </div>

    <div class="mt-3 grid grid-cols-2 gap-2">
      <Select v-model="paymentKind" :options="[{ label: 'Prepaid', value: 'prepaid' }, { label: 'Cash on delivery', value: 'cod' }]" />
      <Select v-model="shopper" :options="[{ label: 'Returning shopper', value: 'returning' }, { label: 'New shopper', value: 'new' }]" />
    </div>

    <template v-if="result">
      <dl class="mt-4 space-y-1.5 border-t border-outline-gray-1 pt-3 text-p-sm">
        <div class="flex justify-between text-ink-gray-7"><dt>Subtotal</dt><dd class="tabular-nums">{{ money(result.subtotal) }}</dd></div>
        <div class="flex justify-between text-ink-gray-7">
          <dt>Discount</dt><dd class="tabular-nums" :class="{ 'text-ink-green-5': result.discount }">−{{ money(result.discount) }}</dd>
        </div>
        <div class="flex justify-between text-base-medium text-ink-gray-8"><dt>Total</dt><dd class="tabular-nums">{{ money(result.total) }}</dd></div>
      </dl>
      <p v-for="reason in result.reasons" :key="reason" class="mt-2 flex items-center gap-1.5 text-p-sm text-ink-amber-6">
        <span class="lucide-circle-alert size-3.5 shrink-0" aria-hidden="true" />{{ reason }}
      </p>
    </template>
  </section>
</template>
