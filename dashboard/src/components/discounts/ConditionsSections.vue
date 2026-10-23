<script setup>
import { computed } from 'vue'
import { Checkbox, FormControl, MultiSelect, Radio, RadioGroup } from 'frappe-ui'
import DiscountSection from './DiscountSection.vue'
import SearchMultiSelect from './SearchMultiSelect.vue'
import { audienceLine, combinationLine, minimumLine, paymentLine } from '../../data/discounts'

const discount = defineModel('discount', { type: Object, required: true })
const props = defineProps({
  customerGroupOptions: { type: Array, default: () => [] },
  showErrors: { type: Boolean, default: false },
})

const minimumSummary = computed(() => minimumLine(discount.value) ?? 'No minimum')
const audienceSummary = computed(
  () => `${audienceLine(discount.value) ?? 'Everyone'} · ${paymentLine(discount.value) ?? 'Any payment method'}`,
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
  props.showErrors && !customerGroups.value.length ? 'Choose at least one group. Without one, nobody can use this discount.' : null,
)
const customerError = computed(() =>
  props.showErrors && !customers.value.length ? 'Choose at least one customer. Without one, nobody can use this discount.' : null,
)
</script>

<template>
  <DiscountSection
    v-if="discount.discount_type !== 'Buy X Get Y' && !discount.tiered"
    title="Minimum purchase"
    collapsible
    :summary="minimumSummary"
    :default-open="discount.minimum_requirement !== 'None'"
  >
    <RadioGroup v-model="discount.minimum_requirement" aria-label="Minimum purchase">
      <Radio value="None" label="None" />
      <Radio value="Subtotal" label="Minimum subtotal" />
      <Radio value="Quantity" label="Minimum number of items" />
    </RadioGroup>
    <FormControl
      v-if="discount.minimum_requirement === 'Subtotal'"
      v-model="discount.minimum_subtotal"
      type="number"
      class="sm:w-48"
      label="Subtotal"
    />
    <FormControl
      v-if="discount.minimum_requirement === 'Quantity'"
      v-model="discount.minimum_quantity"
      type="number"
      class="sm:w-48"
      label="Items"
    />
  </DiscountSection>

  <DiscountSection title="Who can use it" collapsible :summary="audienceSummary">
    <RadioGroup v-model="discount.eligibility" label="Customers">
      <Radio value="Everyone" label="Everyone, guests included" />
      <Radio value="First Order" label="First order only" description="Checked by customer and email, so guests count too." />
      <Radio value="Customer Groups" label="Customer groups" />
      <Radio value="Specific Customers" label="Specific customers" description="Signed-in customers only, up to 100." />
    </RadioGroup>
    <MultiSelect
      v-if="discount.eligibility === 'Customer Groups'"
      v-model="customerGroups"
      :options="customerGroupOptions"
      label="Customer groups"
      placeholder="Choose customer groups"
      :error="groupError"
    />
    <SearchMultiSelect
      v-if="discount.eligibility === 'Specific Customers'"
      v-model="customers"
      target-type="Customer"
      label="Chosen customers"
      placeholder="Search customers"
      :known-labels="customerNames"
      :error="customerError"
    />
    <FormControl
      v-model="discount.payment_condition"
      type="select"
      label="Payment"
      class="sm:w-72"
      :options="[
        { label: 'Any payment method', value: 'Any' },
        { label: 'Prepaid only (not cash on delivery)', value: 'Prepaid' },
        { label: 'Cash on delivery only', value: 'Cash On Delivery' },
      ]"
    />
  </DiscountSection>

  <DiscountSection
    title="Combinations"
    collapsible
    :summary="combinationLine(discount)"
    description="Two discounts stack only when each allows the other."
  >
    <div class="flex flex-col gap-3">
      <Checkbox v-model="discount.combines_with_product" label="Product discounts" />
      <Checkbox v-model="discount.combines_with_order" label="Order discounts" />
      <Checkbox v-model="discount.combines_with_shipping" label="Shipping discounts" />
    </div>
  </DiscountSection>
</template>
