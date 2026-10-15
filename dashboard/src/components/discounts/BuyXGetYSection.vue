<script setup>
import { FormControl, Radio, RadioGroup } from 'frappe-ui'
import DiscountSection from './DiscountSection.vue'
import TargetPicker from './TargetPicker.vue'

const discount = defineModel('discount', { type: Object, required: true })
</script>

<template>
  <DiscountSection title="Customer buys">
    <RadioGroup v-model="discount.buy_requirement" orientation="horizontal">
      <Radio value="Quantity" label="Minimum quantity" />
      <Radio value="Amount" label="Minimum amount" />
    </RadioGroup>
    <div class="grid gap-4 sm:grid-cols-[8rem_1fr]">
      <FormControl
        v-model="discount.buy_value"
        type="number"
        :label="discount.buy_requirement === 'Quantity' ? 'Quantity' : 'Amount'"
      />
      <div>
        <p class="mb-1.5 text-xs text-ink-gray-5">Of any of</p>
        <TargetPicker v-model="discount.targets" role="Buys" target-type="Item" placeholder="Search products" />
      </div>
    </div>
  </DiscountSection>

  <DiscountSection title="Customer gets" description="These items must be in the cart; the discount does not add them.">
    <div class="grid gap-4 sm:grid-cols-[8rem_1fr]">
      <FormControl v-model="discount.get_quantity" type="number" label="Quantity" />
      <div>
        <p class="mb-1.5 text-xs text-ink-gray-5">Of any of</p>
        <TargetPicker v-model="discount.targets" role="Gets" target-type="Item" placeholder="Search products" />
      </div>
    </div>
    <RadioGroup v-model="discount.get_value_type" label="At a discounted value">
      <Radio value="Free" label="Free" />
      <Radio value="Percentage" label="Percentage off" />
      <Radio value="Fixed Amount" label="Amount off each" />
    </RadioGroup>
    <FormControl
      v-if="discount.get_value_type !== 'Free'"
      v-model="discount.get_value"
      type="number"
      class="sm:w-48"
      :label="discount.get_value_type === 'Percentage' ? 'Discount (%)' : 'Discount amount'"
    />
    <FormControl
      v-model="discount.uses_per_order"
      type="number"
      class="sm:w-48"
      label="Maximum uses per order"
      description="0 means as many times as the cart allows."
    />
  </DiscountSection>
</template>
