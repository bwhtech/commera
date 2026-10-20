<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Button,
  Checkbox,
  DatePicker,
  Dropdown,
  FormControl,
  LoadingText,
  MultiSelect,
  Radio,
  RadioGroup,
  Switch,
  TabList,
  TabPanel,
  TabTrigger,
  Tabs,
  dialog,
  toast,
} from 'frappe-ui'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import EmptyState from '../components/EmptyState.vue'
import DiscountSection from '../components/discounts/DiscountSection.vue'
import CodeSection from '../components/discounts/CodeSection.vue'
import ValueSection from '../components/discounts/ValueSection.vue'
import AppliesToSection from '../components/discounts/AppliesToSection.vue'
import BuyXGetYSection from '../components/discounts/BuyXGetYSection.vue'
import ShippingSection from '../components/discounts/ShippingSection.vue'
import DiscountSummary from '../components/discounts/DiscountSummary.vue'
import DiscountTestCart from '../components/discounts/DiscountTestCart.vue'
import {
  blankDiscount,
  deleteDiscount,
  discountTypeBySlug,
  getDiscount,
  getEditorOptions,
  saveDiscount,
} from '../data/discounts'
import { errorMessage } from '../data/errors'
import { money } from '../data/format'

const route = useRoute()
const router = useRouter()

const TABS = [
  { value: 'setup', label: 'Setup', icon: 'lucide-sliders-horizontal' },
  { value: 'conditions', label: 'Conditions', icon: 'lucide-list-checks' },
  { value: 'limits', label: 'Limits and dates', icon: 'lucide-calendar-clock' },
  { value: 'reporting', label: 'Reporting', icon: 'lucide-chart-column' },
]

const discount = ref(null)
const options = ref({ customer_groups: [], campaigns: [], discount_accounts: [], delivery_options: [] })
const loadError = ref(null)
const saving = ref(false)
const tab = ref('setup')

const isNew = computed(() => !discount.value?.name)
const heading = computed(() => {
  if (!discount.value || isNew.value) return 'New discount'
  return discount.value.method === 'Code' ? discount.value.code || discount.value.title : discount.value.title
})

async function load() {
  loadError.value = null
  options.value = (await getEditorOptions()) ?? options.value
  if (route.name === 'DiscountNew') {
    const type = discountTypeBySlug[route.params.type] ?? discountTypeBySlug.products
    discount.value = blankDiscount(type.value, options.value.currency)
    return
  }
  const { data, error } = await getDiscount(route.params.id)
  loadError.value = error
  discount.value = data
}

watch(
  () => [route.name, route.params.id, route.params.type],
  () => {
    // A create that just saved replaces the url with its own name — already loaded.
    if (route.params.id && route.params.id === discount.value?.name) return
    load()
  },
  { immediate: true },
)

async function save() {
  saving.value = true
  try {
    const wasNew = isNew.value
    const saved = await saveDiscount(discount.value)
    if (!saved) return
    discount.value = saved
    toast.success(wasNew ? 'Discount created' : 'Saved')
    if (wasNew) router.replace({ name: 'DiscountDetail', params: { id: saved.name } })
  } finally {
    saving.value = false
  }
}

// Saves the switch alone, so flipping it never publishes edits still waiting for Save.
async function toggleEnabled(enabled) {
  const saved = await saveDiscount({ name: discount.value.name, enabled: enabled ? 1 : 0 })
  if (!saved) return
  Object.assign(discount.value, { enabled: saved.enabled, status: saved.status })
  toast.success(saved.enabled ? 'Discount switched on' : 'Discount switched off')
}

function remove() {
  dialog.danger({
    title: `Delete ${heading.value}?`,
    message: 'Shoppers can no longer use it. A discount orders already used is kept; switch it off instead.',
    confirmLabel: 'Delete discount',
    onConfirm: async ({ setError }) => {
      const { error } = await deleteDiscount(discount.value.name)
      if (error) {
        setError(errorMessage(error))
        return
      }
      toast.success('Discount deleted')
      router.replace('/discounts')
    },
  })
}

const hasValue = computed(() => ['Amount Off Products', 'Amount Off Order'].includes(discount.value?.discount_type))

// One line for each collapsed section's header, so a closed section still says what it holds.
const minimumSummary = computed(() => {
  const value = discount.value
  if (value.minimum_requirement === 'Subtotal') return `Subtotal of ${money(value.minimum_subtotal)} or more`
  if (value.minimum_requirement === 'Quantity') return `${value.minimum_quantity} items or more`
  return 'No minimum'
})
const audienceSummary = computed(() => {
  const value = discount.value
  const customers = { 'First Order': 'First order only', 'Customer Groups': 'Chosen customer groups' }[value.eligibility] ?? 'Everyone'
  const payment = { Prepaid: 'prepaid only', 'Cash On Delivery': 'cash on delivery only' }[value.payment_condition] ?? 'any payment'
  return `${customers} · ${payment}`
})
const combinationSummary = computed(() => {
  const value = discount.value
  const classes = [
    value.combines_with_product && 'product',
    value.combines_with_order && 'order',
    value.combines_with_shipping && 'shipping',
  ].filter(Boolean)
  return classes.length ? `Combines with ${classes.join(', ')} discounts` : 'Combines with nothing'
})
const limitSummary = computed(() => {
  const value = discount.value
  const limits = [
    Number(value.usage_limit) && `${value.usage_limit} uses`,
    value.once_per_customer && 'once per customer',
    Number(value.budget) && `budget ${money(value.budget)}`,
  ].filter(Boolean)
  return limits.length ? limits.join(' · ') : 'No limits'
})

const hasEndDate = computed({
  get: () => Boolean(discount.value.ends_on),
  set: (hasEnd) => (discount.value.ends_on = hasEnd ? discount.value.starts_on : null),
})

const customerGroups = computed({
  get: () => discount.value.customer_groups.map((row) => row.customer_group),
  set: (groups) => (discount.value.customer_groups = groups.map((customer_group) => ({ customer_group }))),
})
</script>

<template>
  <AppPageHeader
    :title="heading"
    back-to="/discounts"
    :breadcrumbs="[{ label: 'Discounts', route: '/discounts' }, { label: heading }]"
  >
    <template v-if="discount" #actions>
      <!-- A phone has no room for the switch beside the title; it moves into the menu. -->
      <Switch
        v-if="!isNew"
        :model-value="Boolean(discount.enabled)"
        class="max-sm:hidden"
        label="Active"
        @update:model-value="toggleEnabled"
      />
      <Dropdown
        v-if="!isNew"
        :options="[
          { label: discount.enabled ? 'Switch off' : 'Switch on', icon: 'power', onClick: () => toggleEnabled(!discount.enabled) },
          { label: 'Delete discount', icon: 'trash-2', theme: 'red', onClick: remove },
        ]"
      >
        <Button icon="lucide-ellipsis" label="More actions" />
      </Dropdown>
      <Button label="Save" variant="solid" theme="gray" :loading="saving" @click="save" />
    </template>
  </AppPageHeader>

  <PageBody width="wide">
    <EmptyState
      v-if="loadError"
      icon="lucide-triangle-alert"
      title="Could not load this discount"
      :description="errorMessage(loadError)"
    />
    <LoadingText v-else-if="!discount" />

    <!-- The summary column sits beside the form from lg; below it the summary comes first,
         so a phone reads what the discount does before the fields that make it. -->
    <div v-else class="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <Tabs v-model="tab" class="order-2 min-w-0 lg:order-1">
        <TabList variant="underline">
          <TabTrigger v-for="item in TABS" :key="item.value" :value="item.value" :label="item.label" :icon-left="item.icon" />
        </TabList>

        <TabPanel value="setup">
          <div class="space-y-5 pt-5">
            <CodeSection v-model:discount="discount" @codes-created="load" />
            <ValueSection v-if="hasValue" v-model:discount="discount" />
            <AppliesToSection v-if="discount.discount_type === 'Amount Off Products'" v-model:discount="discount" />
            <BuyXGetYSection v-if="discount.discount_type === 'Buy X Get Y'" v-model:discount="discount" />
            <ShippingSection
              v-if="discount.discount_type === 'Free Shipping'"
              v-model:discount="discount"
              :delivery-options="options.delivery_options"
            />
          </div>
        </TabPanel>

        <TabPanel value="conditions">
          <div class="space-y-5 pt-5">
            <DiscountSection
              v-if="discount.discount_type !== 'Buy X Get Y' && !discount.tiered"
              title="Minimum purchase"
              collapsible
              :summary="minimumSummary"
              :default-open="discount.minimum_requirement !== 'None'"
            >
              <RadioGroup v-model="discount.minimum_requirement">
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
              </RadioGroup>
              <MultiSelect
                v-if="discount.eligibility === 'Customer Groups'"
                v-model="customerGroups"
                :options="options.customer_groups"
                placeholder="Choose customer groups"
                :error="customerGroups.length ? null : 'Choose at least one group. Without one, nobody can use this discount.'"
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
              :summary="combinationSummary"
              description="Two discounts stack only when each allows the other."
            >
              <div class="flex flex-col gap-3">
                <Checkbox v-model="discount.combines_with_product" label="Product discounts" />
                <Checkbox v-model="discount.combines_with_order" label="Order discounts" />
                <Checkbox v-model="discount.combines_with_shipping" label="Shipping discounts" />
              </div>
            </DiscountSection>
          </div>
        </TabPanel>

        <TabPanel value="limits">
          <div class="space-y-5 pt-5">
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
                <FormControl
                  v-model="discount.budget"
                  type="number"
                  label="Budget"
                  description="Stops once this much discount is given."
                />
              </div>
              <Checkbox v-model="discount.once_per_customer" label="Once per customer" description="Matched by customer, email or phone." />
            </DiscountSection>
          </div>
        </TabPanel>

        <TabPanel value="reporting">
          <div class="space-y-5 pt-5">
            <DiscountSection title="Reporting and accounting" description="Optional. Kept on every order the discount touches.">
              <div class="grid gap-4 sm:grid-cols-2">
                <FormControl
                  v-model="discount.campaign"
                  type="select"
                  label="Campaign"
                  :options="['', ...options.campaigns]"
                  description="The ERPNext Campaign this discount belongs to."
                />
                <FormControl
                  v-model="discount.discount_account"
                  type="select"
                  label="Discount account"
                  :options="['', ...options.discount_accounts]"
                  description="Used when Discount Accounting is on."
                />
              </div>
            </DiscountSection>
          </div>
        </TabPanel>
      </Tabs>

      <aside class="order-1 space-y-5 lg:sticky lg:top-5 lg:order-2">
        <DiscountSummary :discount="discount" />
        <DiscountTestCart v-if="discount.discount_type !== 'Free Shipping'" :discount="discount" />
      </aside>
    </div>
  </PageBody>
</template>
