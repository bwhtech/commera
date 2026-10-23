<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, Dropdown, LoadingText, Switch, TabList, TabPanel, TabTrigger, Tabs, dialog, toast } from 'frappe-ui'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import EmptyState from '../components/EmptyState.vue'
import CodeSection from '../components/discounts/CodeSection.vue'
import ValueSection from '../components/discounts/ValueSection.vue'
import AppliesToSection from '../components/discounts/AppliesToSection.vue'
import BuyXGetYSection from '../components/discounts/BuyXGetYSection.vue'
import ShippingSection from '../components/discounts/ShippingSection.vue'
import ConditionsSections from '../components/discounts/ConditionsSections.vue'
import LimitsSections from '../components/discounts/LimitsSections.vue'
import ReportingSection from '../components/discounts/ReportingSection.vue'
import DiscountSummary from '../components/discounts/DiscountSummary.vue'
import DiscountTestCart from '../components/discounts/DiscountTestCart.vue'
import {
  blankDiscount,
  deleteDiscount,
  discountHeading,
  discountTypeBySlug,
  getDiscount,
  getEditorOptions,
  saveDiscount,
} from '../data/discounts'
import { errorMessage } from '../data/errors'

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
const triedSaving = ref(false)
const tab = ref('setup')

const isNew = computed(() => !discount.value?.name)
const heading = computed(() => (!discount.value || isNew.value ? 'New discount' : discountHeading(discount.value)))

async function load() {
  loadError.value = null
  triedSaving.value = false
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
  triedSaving.value = true
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
    message: "Shoppers can no longer use it. Discounts already used on orders can't be deleted; switch it off instead.",
    confirmLabel: 'Delete discount',
    onConfirm: async () => {
      if (!(await deleteDiscount(discount.value.name))) return
      toast.success('Discount deleted')
      router.replace('/discounts')
    },
  })
}

const hasValue = computed(() => ['Amount Off Products', 'Amount Off Order'].includes(discount.value?.discount_type))
</script>

<template>
  <AppPageHeader
    :title="heading"
    back-to="/discounts"
    :breadcrumbs="[{ label: 'Discounts', route: '/discounts' }, { label: heading }]"
  >
    <template v-if="discount" #actions>
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
          { label: discount.enabled ? 'Switch off' : 'Switch on', icon: 'lucide-power', onClick: () => toggleEnabled(!discount.enabled) },
          { label: 'Delete discount', icon: 'lucide-trash-2', theme: 'red', onClick: remove },
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

    <div v-else class="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <Tabs v-model="tab" class="order-2 min-w-0 lg:order-1">
        <TabList variant="underline">
          <TabTrigger v-for="item in TABS" :key="item.value" :value="item.value" :label="item.label" :icon-left="item.icon" />
        </TabList>

        <TabPanel value="setup">
          <div class="space-y-5 pt-5">
            <CodeSection v-model:discount="discount" />
            <ValueSection v-if="hasValue" v-model:discount="discount" :currencies="options.currencies" :company-currency="options.currency" />
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
            <ConditionsSections
              v-model:discount="discount"
              :customer-group-options="options.customer_groups"
              :show-errors="triedSaving"
            />
          </div>
        </TabPanel>

        <TabPanel value="limits">
          <div class="space-y-5 pt-5">
            <LimitsSections v-model:discount="discount" />
          </div>
        </TabPanel>

        <TabPanel value="reporting">
          <div class="space-y-5 pt-5">
            <ReportingSection
              v-model:discount="discount"
              :campaigns="options.campaigns"
              :discount-accounts="options.discount_accounts"
            />
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
