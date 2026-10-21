<script setup>
import { computed } from 'vue'
import { Button, Checkbox, FormControl, TabButtons } from 'frappe-ui'
import DiscountSection from './DiscountSection.vue'

const discount = defineModel('discount', { type: Object, required: true })
const props = defineProps({
  currencies: { type: Array, default: () => [] },
  companyCurrency: { type: String, default: '' },
})

const isFixed = computed(() => discount.value.value_type === 'Fixed Amount')
// A blank currency is the company currency.
const currency = computed({
  get: () => discount.value.currency || props.companyCurrency,
  set: (value) => (discount.value.currency = value),
})
const currencySymbol = computed(
  () => props.currencies.find((option) => option.value === currency.value)?.symbol || currency.value,
)

const VALUE_TYPES = [
  { label: 'Percentage', value: 'Percentage' },
  { label: 'Fixed amount', value: 'Fixed Amount' },
]

function addTier() {
  const last = discount.value.tiers.at(-1)
  discount.value.tiers.push({
    minimum_subtotal: Number(last?.minimum_subtotal ?? 0) + 2000,
    value: Number(last?.value ?? 5) + 5,
  })
}
</script>

<template>
  <DiscountSection title="Value">
    <TabButtons v-model="discount.value_type" size="sm" :options="VALUE_TYPES" />

    <div v-if="!discount.tiered || isFixed" class="grid gap-4 sm:grid-cols-2">
      <FormControl
        v-if="!discount.tiered"
        v-model="discount.value"
        type="number"
        :label="discount.value_type === 'Percentage' ? 'Discount (%)' : 'Discount amount'"
      >
        <template v-if="isFixed" #prefix><span class="text-sm text-ink-gray-5">{{ currencySymbol }}</span></template>
      </FormControl>
      <FormControl
        v-if="isFixed"
        v-model="currency"
        type="select"
        label="Currency"
        :options="currencies"
        description="Carts in another currency get it converted."
      />
      <FormControl
        v-if="!discount.tiered && discount.value_type === 'Percentage'"
        v-model="discount.maximum_discount"
        type="number"
        label="Maximum discount"
        description="“10% off, up to 200”. 0 means no cap."
      />
    </div>

    <FormControl
      v-if="discount.discount_type === 'Amount Off Products' && discount.value_type === 'Fixed Amount'"
      v-model="discount.fixed_applies_to"
      type="select"
      label="The amount comes off"
      :options="[
        { label: 'Each eligible item', value: 'Each Item' },
        { label: 'Once per order, spread over eligible items', value: 'Once Per Order' },
      ]"
    />

    <template v-if="discount.discount_type === 'Amount Off Order'">
      <Checkbox
        v-model="discount.exclude_sale_items"
        label="Skip items already on sale"
        description="Their amount does not count towards the discount."
      />
      <Checkbox
        v-model="discount.tiered"
        label="Spend more, save more"
        description="The best tier the subtotal reaches applies."
      />
      <div v-if="discount.tiered" class="space-y-2">
        <div
          v-for="(tier, index) in discount.tiers"
          :key="index"
          class="grid grid-cols-[1fr_1fr_auto] items-end gap-2"
        >
          <FormControl v-model="tier.minimum_subtotal" type="number" :label="index ? '' : 'Subtotal from'" />
          <FormControl
            v-model="tier.value"
            type="number"
            :label="index ? '' : discount.value_type === 'Percentage' ? 'Discount (%)' : 'Discount amount'"
          >
            <template v-if="isFixed" #prefix><span class="text-sm text-ink-gray-5">{{ currencySymbol }}</span></template>
          </FormControl>
          <Button icon="lucide-x" variant="ghost" :aria-label="`Remove tier ${index + 1}`" @click="discount.tiers.splice(index, 1)" />
        </div>
        <Button label="Add tier" icon-left="lucide-plus" @click="addTier" />
      </div>
    </template>
  </DiscountSection>
</template>
