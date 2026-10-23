<script setup>
import { computed } from 'vue'
import { FormControl, MultiSelect } from 'frappe-ui'
import DiscountSection from './DiscountSection.vue'

const discount = defineModel('discount', { type: Object, required: true })
defineProps({ deliveryOptions: { type: Array, default: () => [] } })

// Stored one title per line, the way Desk shows it; the picker edits it as a list.
const chosenOptions = computed({
  get: () => (discount.value.delivery_options || '').split('\n').filter(Boolean),
  set: (titles) => (discount.value.delivery_options = titles.join('\n')),
})
</script>

<template>
  <DiscountSection title="Delivery">
    <MultiSelect v-model="chosenOptions" :options="deliveryOptions" label="Delivery options" placeholder="Every delivery option" />
    <div class="grid gap-4 sm:grid-cols-2">
      <FormControl
        v-model="discount.shipping_percentage"
        type="number"
        label="Off the delivery charge (%)"
        description="100 makes delivery free."
      />
      <FormControl
        v-model="discount.maximum_shipping_rate"
        type="number"
        label="Skip rates above"
        description="Keeps expensive options at full price. 0 means no limit."
      />
    </div>
  </DiscountSection>
</template>
