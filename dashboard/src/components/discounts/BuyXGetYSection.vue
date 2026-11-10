<script setup>
import { FormControl, Radio, RadioGroup } from 'frappe-ui'
import DiscountSection from './DiscountSection.vue'
import TargetPicker from './TargetPicker.vue'

const discount = defineModel('discount', { type: Object, required: true })
</script>

<template>
  <DiscountSection :title="__('Customer buys')">
    <RadioGroup v-model="discount.buy_requirement" orientation="horizontal" :aria-label="__('Customer buys')">
      <Radio value="Quantity" :label="__('Minimum quantity')" />
      <Radio value="Amount" :label="__('Minimum amount')" />
    </RadioGroup>
    <div class="grid gap-4 sm:grid-cols-[8rem_1fr]">
      <FormControl
        v-model="discount.buy_value"
        type="number"
        :label="discount.buy_requirement === 'Quantity' ? __('Quantity') : __('Amount')"
      />
      <TargetPicker v-model="discount.targets" role="Buys" target-type="Item" :label="__('Buys any of')" :placeholder="__('Search products')" />
    </div>
  </DiscountSection>

  <DiscountSection :title="__('Customer gets')" :description="__('These items must be in the cart; the discount does not add them.')">
    <div class="grid gap-4 sm:grid-cols-[8rem_1fr]">
      <FormControl v-model="discount.get_quantity" type="number" :label="__('Quantity')" />
      <TargetPicker v-model="discount.targets" role="Gets" target-type="Item" :label="__('Gets any of')" :placeholder="__('Search products')" />
    </div>
    <RadioGroup v-model="discount.get_value_type" :label="__('At a discounted value')">
      <Radio value="Free" :label="__('Free')" />
      <Radio value="Percentage" :label="__('Percentage off')" />
      <Radio value="Fixed Amount" :label="__('Amount off each')" />
    </RadioGroup>
    <FormControl
      v-if="discount.get_value_type !== 'Free'"
      v-model="discount.get_value"
      type="number"
      class="sm:w-48"
      :label="discount.get_value_type === 'Percentage' ? __('Discount (%)') : __('Discount amount')"
    />
    <FormControl
      v-model="discount.uses_per_order"
      type="number"
      class="sm:w-48"
      :label="__('Maximum uses per order')"
      :description="__('0 means as many times as the cart allows.')"
    />
  </DiscountSection>
</template>
