<script setup>
import { computed } from 'vue'
import { Checkbox, FormControl, MultiSelect, Radio, RadioGroup } from 'frappe-ui'
import DiscountSection from './DiscountSection.vue'
import SearchMultiSelect from './SearchMultiSelect.vue'
import { audienceLine, combinationLine, minimumLine, paymentLine } from '../../data/discounts'
import { __ } from '../../data/translation'

const discount = defineModel('discount', { type: Object, required: true })
const props = defineProps({
  customerGroupOptions: { type: Array, default: () => [] },
  showErrors: { type: Boolean, default: false },
})

const minimumSummary = computed(() => minimumLine(discount.value) ?? __('No minimum'))
const audienceSummary = computed(
  () => `${audienceLine(discount.value) ?? __('Everyone')} · ${paymentLine(discount.value) ?? __('Any payment method')}`,
)

const customerGroups = computed({
  get: () => discount.value.customer_groups.map((row) => row.customer_group),
  set: (groups) => (discount.value.customer_groups = groups.map((customer_group) => ({ customer_group }))),
})

const customerNames = computed(() =>
  Object.fromEntries(discount.value.customers.map((row) => [row.customer, row.customer_name || row.customer])),
)
const customers = computed({
  get: () => discount.value.customers.map((row) => row.customer),
  set: (names) => (discount.value.customers = names.map((customer) => ({ customer, customer_name: customerNames.value[customer] }))),
})

const groupError = computed(() =>
  props.showErrors && !customerGroups.value.length ? __('Choose at least one group. Without one, nobody can use this discount.') : null,
)
const customerError = computed(() =>
  props.showErrors && !customers.value.length ? __('Choose at least one customer. Without one, nobody can use this discount.') : null,
)
</script>

<template>
  <DiscountSection
    v-if="discount.discount_type !== 'Buy X Get Y' && !discount.tiered"
    :title="__('Minimum purchase')"
    collapsible
    :summary="minimumSummary"
    :default-open="discount.minimum_requirement !== 'None'"
  >
    <RadioGroup v-model="discount.minimum_requirement" :aria-label="__('Minimum purchase')">
      <Radio value="None" :label="__('None')" />
      <Radio value="Subtotal" :label="__('Minimum subtotal')" />
      <Radio value="Quantity" :label="__('Minimum number of items')" />
    </RadioGroup>
    <FormControl
      v-if="discount.minimum_requirement === 'Subtotal'"
      v-model="discount.minimum_subtotal"
      type="number"
      class="sm:w-48"
      :label="__('Subtotal')"
    />
    <FormControl
      v-if="discount.minimum_requirement === 'Quantity'"
      v-model="discount.minimum_quantity"
      type="number"
      class="sm:w-48"
      :label="__('Items')"
    />
  </DiscountSection>

  <DiscountSection :title="__('Who can use it')" collapsible :summary="audienceSummary">
    <RadioGroup v-model="discount.eligibility" :label="__('Customers')">
      <Radio value="Everyone" :label="__('Everyone, guests included')" />
      <Radio value="First Order" :label="__('First order only')" :description="__('Checked by customer and email, so guests count too.')" />
      <Radio value="Customer Groups" :label="__('Customer groups')" />
      <Radio value="Specific Customers" :label="__('Specific customers')" :description="__('Signed-in customers only, up to 100.')" />
    </RadioGroup>
    <MultiSelect
      v-if="discount.eligibility === 'Customer Groups'"
      v-model="customerGroups"
      :options="customerGroupOptions"
      :label="__('Customer groups')"
      :placeholder="__('Choose customer groups')"
      :error="groupError"
    />
    <SearchMultiSelect
      v-if="discount.eligibility === 'Specific Customers'"
      v-model="customers"
      target-type="Customer"
      :label="__('Chosen customers')"
      :placeholder="__('Search customers')"
      :known-labels="customerNames"
      :error="customerError"
    />
    <FormControl
      v-model="discount.payment_condition"
      type="select"
      :label="__('Payment')"
      class="sm:w-72"
      :options="[
        { label: __('Any payment method'), value: 'Any' },
        { label: __('Prepaid only (not cash on delivery)'), value: 'Prepaid' },
        { label: __('Cash on delivery only'), value: 'Cash On Delivery' },
      ]"
    />
  </DiscountSection>

  <DiscountSection
    :title="__('Combinations')"
    collapsible
    :summary="combinationLine(discount)"
    :description="__('Two discounts stack only when each allows the other.')"
  >
    <div class="flex flex-col gap-3">
      <Checkbox v-model="discount.combines_with_product" :label="__('Product discounts')" />
      <Checkbox v-model="discount.combines_with_order" :label="__('Order discounts')" />
      <Checkbox v-model="discount.combines_with_shipping" :label="__('Shipping discounts')" />
    </div>
  </DiscountSection>
</template>
