<script setup>
import { computed, ref, watch } from 'vue'
import { Combobox, FormControl, Select, TextInput } from 'frappe-ui'
import { getCountryDefaults, storeSetup } from '../../../data/onboarding'
import { CATEGORIES, draft, flow } from '../../../ia/onboarding'
import { abbreviate, missingField, toOptions } from '../../../ia/onboardingSteps'
import { sendSetupEvent } from '../../../data/setupFunnel'

const props = defineProps({
  record: { type: Object, required: true },
})

const MONTHS = Array.from({ length: 12 }, (_, index) => ({
  label: new Date(2000, index, 1).toLocaleString(undefined, { month: 'long' }),
  value: index + 1,
}))

// The charts on offer follow the picked country; the stored country's list arrives with the record.
const STANDARD_CHARTS = ['Standard', 'Standard with Numbers']
const countryCharts = ref(null)

const showAccounting = ref(false)

function toggleAccounting() {
  showAccounting.value = !showAccounting.value
  if (showAccounting.value) sendSetupEvent('onboarding_accounting_opened')
}
const missing = computed(() => (flow.showErrors ? missingField('store', draft) : ''))

// Once setup has made the company, its country, currency and books are fixed.
const isLocked = computed(() => storeSetup.status === 'running' || storeSetup.status === 'done')

const options = computed(() => props.record.options ?? {})
const chartOptions = computed(() =>
  toOptions(countryCharts.value ?? options.value.charts_of_accounts ?? STANDARD_CHARTS),
)
const accountingSummary = computed(() =>
  [draft.currency, draft.timeZone, draft.chartOfAccounts === 'Standard' ? 'Standard accounts' : draft.chartOfAccounts]
    .filter(Boolean)
    .join(' · '),
)

watch(
  () => draft.country,
  async (country, previous) => {
    // A fresh site starts with no country, so the first pick must fill its defaults too.
    if (!country || country === previous || isLocked.value) return
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
      label="Store name"
      autocomplete="organization"
      :error="missing === 'storeName' ? 'Required' : ''"
    />

    <div>
      <p class="mb-2 text-xs" :class="missing === 'storeCategory' ? 'text-ink-red-6' : 'text-ink-gray-6'">You sell</p>
      <div class="grid grid-cols-3 gap-2">
        <button
          v-for="option in CATEGORIES"
          :key="option.value"
          type="button"
          class="flex flex-col items-center gap-2 rounded-4 border px-2 py-3 text-sm transition-[background-color,border-color,color,transform] duration-150 ease-out-strong active:scale-[0.97]"
          :class="
            draft.storeCategory === option.value
              ? 'border-outline-gray-5 bg-surface-gray-2 text-ink-gray-9'
              : 'border-outline-gray-2 text-ink-gray-6 hover:bg-surface-gray-1'
          "
          :aria-pressed="draft.storeCategory === option.value"
          @click="draft.storeCategory = option.value"
        >
          <span :class="option.icon" class="size-5" aria-hidden="true" />
          <span class="truncate">{{ option.value }}</span>
        </button>
      </div>
    </div>

    <Combobox
      v-model="draft.country"
      trigger="button"
      label="Country"
      placeholder="Search countries"
      :options="toOptions(options.countries)"
      :disabled="isLocked"
    />

    <div>
      <button
        type="button"
        class="flex items-center gap-1 text-sm text-ink-gray-5 transition-colors hover:text-ink-gray-7"
        :aria-expanded="showAccounting"
        data-onboarding-accounting
        @click="toggleAccounting"
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
              label="Currency"
              :options="toOptions(options.currencies)"
              :disabled="isLocked"
            />
            <Combobox
              v-model="draft.timeZone"
              trigger="button"
              label="Time zone"
              :options="toOptions(options.time_zones)"
              :disabled="isLocked"
            />
            <Select v-model="draft.chartOfAccounts" label="Chart of accounts" :options="chartOptions" :disabled="isLocked" />
            <Select
              v-model="draft.fiscalYearStartMonth"
              label="Year starts"
              placeholder="Country default"
              :options="MONTHS"
              :disabled="isLocked"
            />
            <TextInput
              v-model="draft.companyAbbr"
              label="Short code"
              :placeholder="abbreviate(draft.storeName)"
              :disabled="isLocked"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
