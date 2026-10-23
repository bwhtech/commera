<script setup>
import { FormControl } from 'frappe-ui'
import DiscountSection from './DiscountSection.vue'

const discount = defineModel('discount', { type: Object, required: true })
defineProps({
  campaigns: { type: Array, default: () => [] },
  discountAccounts: { type: Array, default: () => [] },
})
</script>

<template>
  <DiscountSection title="Reporting and accounting" description="Optional. Kept on every order the discount touches.">
    <div class="grid gap-4 sm:grid-cols-2">
      <FormControl
        v-model="discount.campaign"
        type="select"
        label="Campaign"
        :options="['', ...campaigns]"
        description="The marketing campaign orders using this discount are tagged with."
      />
      <FormControl
        v-model="discount.discount_account"
        type="select"
        label="Discount account"
        :options="['', ...discountAccounts]"
        description="Used when Discount Accounting is on."
      />
    </div>
  </DiscountSection>
</template>
