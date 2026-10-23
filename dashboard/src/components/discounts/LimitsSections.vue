<script setup>
import { computed } from 'vue'
import { Checkbox, DatePicker, FormControl } from 'frappe-ui'
import DiscountSection from './DiscountSection.vue'
import { limitLines } from '../../data/discounts'

const discount = defineModel('discount', { type: Object, required: true })

const limitSummary = computed(() => limitLines(discount.value).join(' · ') || 'No limits')

const hasEndDate = computed({
  get: () => Boolean(discount.value.ends_on),
  set: (hasEnd) => (discount.value.ends_on = hasEnd ? discount.value.starts_on : null),
})
</script>

<template>
  <DiscountSection title="Active dates">
    <div class="grid gap-4 sm:grid-cols-2">
      <DatePicker v-model="discount.starts_on" label="Starts on" />
      <DatePicker v-if="hasEndDate" v-model="discount.ends_on" label="Ends on" />
    </div>
    <Checkbox v-model="hasEndDate" label="Set an end date" />
  </DiscountSection>

  <DiscountSection title="Limits" collapsible :summary="limitSummary" :default-open="limitSummary !== 'No limits'">
    <div class="grid gap-4 sm:grid-cols-2">
      <FormControl v-model="discount.usage_limit" type="number" label="Total uses" description="0 means no limit." />
      <FormControl v-model="discount.budget" type="number" label="Budget" description="Stops once this much discount is given." />
    </div>
    <Checkbox v-model="discount.once_per_customer" label="Once per customer" description="Matched by customer, email or phone." />
  </DiscountSection>
</template>
