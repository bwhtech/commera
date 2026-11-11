<script setup>
import { computed } from 'vue'
import { Checkbox, DatePicker, FormControl } from 'frappe-ui'
import DiscountSection from './DiscountSection.vue'
import { limitLines } from '../../data/discounts'
import { __ } from '../../data/translation'

const discount = defineModel('discount', { type: Object, required: true })

const limitSummary = computed(() => limitLines(discount.value).join(' · ') || __('No limits'))

const hasEndDate = computed({
  get: () => Boolean(discount.value.ends_on),
  set: (hasEnd) => (discount.value.ends_on = hasEnd ? discount.value.starts_on : null),
})
</script>

<template>
  <DiscountSection :title="__('Active dates')">
    <div class="grid gap-4 sm:grid-cols-2">
      <DatePicker v-model="discount.starts_on" :label="__('Starts on')" />
      <DatePicker v-if="hasEndDate" v-model="discount.ends_on" :label="__('Ends on')" />
    </div>
    <Checkbox v-model="hasEndDate" :label="__('Set an end date')" />
  </DiscountSection>

  <DiscountSection :title="__('Limits')" collapsible :summary="limitSummary" :default-open="limitSummary !== __('No limits')">
    <div class="grid gap-4 sm:grid-cols-2">
      <FormControl v-model="discount.usage_limit" type="number" :label="__('Total uses')" :description="__('0 means no limit.')" />
      <FormControl v-model="discount.budget" type="number" :label="__('Budget')" :description="__('Stops once this much discount is given.')" />
    </div>
    <Checkbox v-model="discount.once_per_customer" :label="__('Once per customer')" :description="__('Matched by customer, email or phone.')" />
  </DiscountSection>
</template>
