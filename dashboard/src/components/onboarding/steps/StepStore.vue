<script setup>
import { computed, ref, watch } from 'vue'
import { Button, Combobox, FormControl, Select, Spinner, TextInput, toast, useFileUpload } from 'frappe-ui'
import { getCountryDefaults, storeSetup } from '../../../data/onboarding'
import { CATEGORIES, draft, flow } from '../../../ia/onboarding'
import { abbreviate, missingField, storePicks, toOptions } from '../../../ia/onboardingSteps'
import { monthName } from '../../../data/format'
import { __ } from '../../../data/translation'
import commeraLogo from '../../../assets/commera.svg'

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
const { upload, isUploading } = useFileUpload()
const logoInput = ref(null)
const isDraggingLogo = ref(false)

// Once setup has made the company, its country, currency and books are fixed.
const isLocked = computed(() => storeSetup.status === 'running' || storeSetup.status === 'done')
// start_store_setup leaves a running job alone and writes nothing, so a name changed while it
// runs would be dropped without a word. Once it is done it saves again.
const isRunning = computed(() => storeSetup.status === 'running')

const options = computed(() => props.record.options ?? {})
const chartOptions = computed(() =>
  toOptions(countryCharts.value ?? options.value.charts_of_accounts ?? STANDARD_CHARTS),
)
function chartLabel(chart) {
  return chart === 'Standard' ? __('Standard accounts') : chart
}

const accountingSummary = computed(() =>
  [draft.country || __('Choose a country'), draft.currency, draft.timeZone, chartLabel(draft.chartOfAccounts)]
    .filter(Boolean)
    .join(' · '),
)

const existingStore = computed(() => props.record.existing_store)
const picks = computed(() => storePicks(existingStore.value, draft.company))
const missing = computed(() => (flow.showErrors ? missingField('store', draft, { picks: picks.value }) : ''))
const isAccountingOpen = computed(() => showAccounting.value || missing.value === 'country')

const company = computed(() => existingStore.value?.companies.find((row) => row.name === draft.company))
const companySummary = computed(() =>
  company.value
    ? [company.value.default_currency, company.value.abbr, chartLabel(company.value.chart_of_accounts)]
        .filter(Boolean)
        .join(' · ')
    : '',
)

watch(
  company,
  (picked) => {
    if (!picked) return
    draft.currency = picked.default_currency
    draft.companyAbbr = picked.abbr
    draft.chartOfAccounts = picked.chart_of_accounts
    if (!picks.value.priceLists.includes(draft.priceList)) draft.priceList = ''
  },
  { immediate: true },
)

async function uploadLogo(event) {
  const [file] = [...(event.target.files ?? [])]
  event.target.value = ''
  await uploadLogoFile(file)
}

async function dropLogo(event) {
  isDraggingLogo.value = false
  if (isUploading.value) return
  const [file] = [...(event.dataTransfer?.files ?? [])]
  await uploadLogoFile(file)
}

async function uploadLogoFile(file) {
  if (!file) return
  if (!file.type.startsWith('image/')) {
    toast.error(__('Could not upload {0}', [file.name]))
    return
  }
  try {
    const uploaded = await upload(file, { private: false })
    draft.brandLogo = uploaded.file_url
  } catch {
    toast.error(__('Could not upload {0}', [file.name]))
  }
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
    <div>
      <div class="mb-2 flex items-center justify-between text-xs">
        <p class="text-ink-gray-6">{{ __('Logo') }}</p>
        <p class="text-ink-gray-4">{{ __('Optional') }}</p>
      </div>
      <input ref="logoInput" type="file" accept="image/*" class="hidden" data-onboarding-logo-input @change="uploadLogo" />
      <div class="group relative">
        <button
          type="button"
          class="flex h-20 w-full items-center justify-center gap-2 rounded-4 border border-dashed text-ink-gray-5 transition-[background-color,border-color,transform] duration-150 ease-out-strong hover:bg-surface-gray-1 active:scale-[0.99]"
          :class="isDraggingLogo ? 'border-outline-gray-4 bg-surface-gray-2' : 'border-outline-gray-3'"
          :disabled="isUploading"
          data-onboarding-logo-drop
          @click="logoInput?.click()"
          @dragover.prevent="isDraggingLogo = true"
          @dragleave="isDraggingLogo = false"
          @drop.prevent="dropLogo"
        >
          <Spinner v-if="isUploading" class="size-5" />
          <img v-else-if="draft.brandLogo" :src="draft.brandLogo" :alt="__('Your logo')" class="max-h-12 max-w-[60%] object-contain" />
          <template v-else>
            <img :src="commeraLogo" alt="" class="size-10 rounded-3" />
            <span class="text-sm">{{ __('Upload') }}</span>
          </template>
        </button>
        <Button
          v-if="draft.brandLogo && !isUploading"
          class="absolute end-1 top-1 !size-6 !rounded-full !bg-black-overlay-500 !text-white opacity-100 backdrop-blur-sm transition-opacity hover:!bg-black-overlay-700 sm:opacity-0 sm:group-hover:opacity-100"
          icon="lucide-x"
          :label="__('Remove logo')"
          @click="draft.brandLogo = ''"
        />
      </div>
    </div>

    <FormControl
      v-model="draft.storeName"
      :label="__('Store name')"
      required
      autocomplete="organization"
      :disabled="isRunning"
      :description="isRunning ? __('You can change the name once setup finishes.') : ''"
      :error="missing === 'storeName' ? __('Required') : ''"
    />

    <div>
      <div class="mb-2 flex items-center justify-between text-xs">
        <p class="text-ink-gray-6">{{ __('You sell') }}</p>
        <p class="text-ink-gray-4">{{ __('Optional') }}</p>
      </div>
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
          @click="draft.storeCategory = draft.storeCategory === option.value ? '' : option.value"
        >
          <span :class="option.icon" class="size-5" aria-hidden="true" />
          <span class="truncate">{{ option.label }}</span>
        </button>
      </div>
    </div>

    <template v-if="existingStore">
      <Combobox
        v-if="picks.companies.length"
        v-model="draft.company"
        trigger="button"
        :label="__('Company')"
        required
        :placeholder="__('Pick your company')"
        :options="toOptions(picks.companies)"
        :description="companySummary"
        :error="missing === 'company' ? __('Pick the company your store sells for') : ''"
      />
      <Combobox
        v-if="picks.priceLists.length"
        v-model="draft.priceList"
        trigger="button"
        :label="__('Price list')"
        required
        :placeholder="__('Pick a price list')"
        :options="toOptions(picks.priceLists)"
        :error="missing === 'priceList' ? __('Required') : ''"
      />
    </template>

    <template v-else>
      <div>
        <button
          type="button"
          class="flex items-center gap-1 text-sm transition-colors"
          :class="missing === 'country' ? 'text-ink-red-6' : 'text-ink-gray-5 hover:text-ink-gray-7'"
          :aria-expanded="isAccountingOpen"
          data-onboarding-accounting
          @click="showAccounting = !showAccounting"
        >
          {{ accountingSummary }}
          <span
            class="lucide-chevron-down size-3.5 transition-transform duration-300 ease-in-out-strong"
            :class="{ 'rotate-180': isAccountingOpen }"
            aria-hidden="true"
          />
        </button>
        <!-- A 0fr→1fr grid row is the one height animation CSS can do without measuring; inert keeps the
             closed fields out of the tab order. -->
        <div
          class="grid transition-[grid-template-rows,opacity] duration-300 ease-out-strong"
          :class="isAccountingOpen ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'"
          :inert="!isAccountingOpen"
        >
          <div class="overflow-hidden">
            <div class="grid grid-cols-2 gap-3 pt-3">
              <Combobox
                v-model="draft.country"
                trigger="button"
                class="col-span-2"
                :label="__('Country')"
                required
                :placeholder="__('Search countries')"
                :options="toOptions(options.countries)"
                :disabled="isLocked"
              />
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
