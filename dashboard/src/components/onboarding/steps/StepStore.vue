<script setup>
import { computed, ref, watch } from 'vue'
import { Button, Combobox, FormControl, Select, TextInput } from 'frappe-ui'
import { createSalePriceList, getCountryDefaults, storeSetup } from '../../../data/onboarding'
import { CATEGORIES, draft, flow } from '../../../ia/onboarding'
import { abbreviate, missingField, toOptions } from '../../../ia/onboardingSteps'
import { monthName } from '../../../data/format'
import { __ } from '../../../data/translation'

const props = defineProps({
  record: { type: Object, required: true },
})

const MONTHS = Array.from({ length: 12 }, (_, index) => ({
  label: monthName(index + 1),
  value: index + 1,
}))

// The charts on offer follow the picked country; the stored country's list arrives with the record.
const STANDARD_CHARTS = ['Standard', 'Standard with Numbers']
const countryCharts = ref(null)

const showAccounting = ref(false)
const missing = computed(() => (flow.showErrors ? missingField('store', draft) : ''))

// Once setup has made the company, its country, currency and books are fixed.
const isLocked = computed(() => storeSetup.status === 'running' || storeSetup.status === 'done')
// start_store_setup leaves a running job alone and writes nothing, so a name or category changed
// while it runs would be dropped without a word. Once it is done they save again.
const isRunning = computed(() => storeSetup.status === 'running')

const options = computed(() => props.record.options ?? {})
const chartOptions = computed(() =>
  toOptions(countryCharts.value ?? options.value.charts_of_accounts ?? STANDARD_CHARTS),
)
function chartLabel(chart) {
  return chart === 'Standard' ? __('Standard accounts') : chart
}

const accountingSummary = computed(() =>
  [draft.currency, draft.timeZone, chartLabel(draft.chartOfAccounts)].filter(Boolean).join(' · '),
)

const existingStore = computed(() => props.record.existing_store)
const createdPriceLists = ref([])
const duplicating = ref(false)

const company = computed(() => existingStore.value?.companies.find((row) => row.name === draft.company))
const companyOptions = computed(() => toOptions(existingStore.value?.companies.map((row) => row.name)))
const priceListOptions = computed(() =>
  toOptions(
    [...(existingStore.value?.price_lists ?? []), ...createdPriceLists.value]
      .filter((row) => row.currency === company.value?.default_currency)
      .map((row) => row.name),
  ),
)
const warehouseOptions = computed(() =>
  toOptions(existingStore.value?.warehouses.filter((row) => row.company === draft.company).map((row) => row.name)),
)
const companySummary = computed(() =>
  company.value
    ? [company.value.default_currency, company.value.abbr, chartLabel(company.value.chart_of_accounts)]
        .filter(Boolean)
        .join(' · ')
    : '',
)

function isOffered(options, value) {
  return options.some((option) => option.value === value)
}

watch(
  company,
  (picked) => {
    if (!picked) return
    draft.currency = picked.default_currency
    draft.companyAbbr = picked.abbr
    draft.chartOfAccounts = picked.chart_of_accounts
    if (!isOffered(priceListOptions.value, draft.priceList)) draft.priceList = ''
    if (!isOffered(priceListOptions.value, draft.salePriceList)) draft.salePriceList = draft.priceList
    if (!isOffered(warehouseOptions.value, draft.warehouse)) {
      draft.warehouse = isOffered(warehouseOptions.value, picked.default_warehouse) ? picked.default_warehouse : ''
    }
  },
  { immediate: true },
)

async function duplicateSaleList() {
  duplicating.value = true
  const name = await createSalePriceList({ storeName: draft.storeName, company: draft.company })
  duplicating.value = false
  if (!name) return
  createdPriceLists.value.push({ name, currency: company.value.default_currency })
  draft.salePriceList = name
}

watch(
  () => draft.country,
  async (country, previous) => {
    // A fresh site starts with no country, so the first pick must fill its defaults too.
    if (!country || country === previous || isLocked.value || existingStore.value) return
    draft.fiscalYearStartMonth = null
    if (!STANDARD_CHARTS.includes(draft.chartOfAccounts)) draft.chartOfAccounts = 'Standard'
    const defaults = await getCountryDefaults(country)
    // A slower answer for a country already moved past must not overwrite the newer pick.
    if (!defaults || draft.country !== country) return
    if (defaults.currency) draft.currency = defaults.currency
    if (defaults.timeZone) draft.timeZone = defaults.timeZone
    countryCharts.value = defaults.chartsOfAccounts.length ? defaults.chartsOfAccounts : null
  },
)
</script>

<template>
  <div class="space-y-5">
    <FormControl
      v-model="draft.storeName"
      :label="__('Store name')"
      autocomplete="organization"
      :disabled="isRunning"
      :description="isRunning ? __('You can change the name once setup finishes.') : ''"
      :error="missing === 'storeName' ? __('Required') : ''"
    />

    <div>
      <p class="mb-2 text-xs" :class="missing === 'storeCategory' ? 'text-ink-red-6' : 'text-ink-gray-6'">{{ __('You sell') }}</p>
      <div class="grid grid-cols-3 gap-2">
        <button
          v-for="option in CATEGORIES"
          :key="option.value"
          type="button"
          class="flex flex-col items-center gap-2 rounded-4 border px-2 py-3 text-sm transition-[background-color,border-color,color,transform] duration-150 ease-out-strong enabled:active:scale-[0.97] disabled:cursor-not-allowed"
          :class="
            draft.storeCategory === option.value
              ? 'border-outline-gray-5 bg-surface-gray-2 text-ink-gray-9'
              : 'border-outline-gray-2 text-ink-gray-6 hover:bg-surface-gray-1'
          "
          :aria-pressed="draft.storeCategory === option.value"
          :disabled="isRunning"
          @click="draft.storeCategory = option.value"
        >
          <span :class="option.icon" class="size-5" aria-hidden="true" />
          <span class="truncate">{{ option.label }}</span>
        </button>
      </div>
    </div>

    <template v-if="existingStore">
      <Combobox
        v-model="draft.company"
        trigger="button"
        :label="__('Company')"
        :placeholder="__('Pick your company')"
        :options="companyOptions"
        :description="companySummary"
        :error="missing === 'company' ? __('Pick the company your store sells for') : ''"
      />
      <Combobox
        v-model="draft.priceList"
        trigger="button"
        :label="__('Price list')"
        :placeholder="__('Pick a selling price list')"
        :options="priceListOptions"
        :disabled="!draft.company"
        :error="missing === 'priceList' ? __('Required') : ''"
      />
      <div>
        <div class="flex items-end gap-2">
          <Combobox
            v-model="draft.salePriceList"
            class="min-w-0 flex-1"
            trigger="button"
            :label="__('Sale price list')"
            :placeholder="__('Pick a sale price list')"
            :options="priceListOptions"
            :disabled="!draft.company"
            :error="missing === 'salePriceList' ? __('Required') : ''"
          />
          <Button
            :label="__('Duplicate')"
            :loading="duplicating"
            :disabled="!draft.company || !draft.storeName.trim()"
            data-onboarding-duplicate-sale-list
            @click="duplicateSaleList"
          />
        </div>
        <p class="mt-1.5 text-p-sm text-ink-gray-6">
          {{ __('Pick the price list as the sale list to sell without sale prices, or Duplicate for an empty one.') }}
        </p>
      </div>
      <Combobox
        v-model="draft.warehouse"
        trigger="button"
        :label="__('Warehouse')"
        :placeholder="__('Pick the warehouse you ship from')"
        :options="warehouseOptions"
        :disabled="!draft.company"
        :error="missing === 'warehouse' ? __('Required') : ''"
      />
    </template>

    <template v-else>
      <Combobox
        v-model="draft.country"
        trigger="button"
        :label="__('Country')"
        :placeholder="__('Search countries')"
        :options="toOptions(options.countries)"
        :disabled="isLocked"
      />

      <div>
        <button
          type="button"
          class="flex items-center gap-1 text-sm text-ink-gray-5 transition-colors hover:text-ink-gray-7"
          :aria-expanded="showAccounting"
          data-onboarding-accounting
          @click="showAccounting = !showAccounting"
        >
          {{ accountingSummary }}
          <span
            class="lucide-chevron-down size-3.5 transition-transform duration-300 ease-in-out-strong"
            :class="{ 'rotate-180': showAccounting }"
            aria-hidden="true"
          />
        </button>
        <!-- A 0fr→1fr grid row is the one height animation CSS can do without measuring; inert keeps the
             closed fields out of the tab order. -->
        <div
          class="grid transition-[grid-template-rows,opacity] duration-300 ease-out-strong"
          :class="showAccounting ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'"
          :inert="!showAccounting"
        >
          <div class="overflow-hidden">
            <div class="grid grid-cols-2 gap-3 pt-3">
              <Combobox
                v-model="draft.currency"
                trigger="button"
                :label="__('Currency')"
                :options="toOptions(options.currencies)"
                :disabled="isLocked"
              />
              <Combobox
                v-model="draft.timeZone"
                trigger="button"
                :label="__('Time zone')"
                :options="toOptions(options.time_zones)"
                :disabled="isLocked"
              />
              <Select v-model="draft.chartOfAccounts" :label="__('Chart of accounts')" :options="chartOptions" :disabled="isLocked" />
              <Select
                v-model="draft.fiscalYearStartMonth"
                :label="__('Year starts')"
                :placeholder="__('Country default')"
                :options="MONTHS"
                :disabled="isLocked"
              />
              <TextInput
                v-model="draft.companyAbbr"
                :label="__('Short code')"
                :placeholder="abbreviate(draft.storeName)"
                :disabled="isLocked"
              />
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
