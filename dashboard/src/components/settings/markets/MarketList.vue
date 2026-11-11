<script setup>
import { Badge, Button, SettingsBody, Switch } from 'frappe-ui'
import EmptyState from '../../EmptyState.vue'
import SettingsPanelHeader from '../SettingsPanelHeader.vue'
import SettingsSkeleton from '../SettingsSkeleton.vue'
import { marketStore } from '../../../data/markets'
import { urlSummary } from '../../../data/marketUrls'
import { NEW_MARKET } from '../../../data/useMarketForm'
import { __ } from '../../../data/translation'

const emit = defineEmits(['open'])

const { markets, choices, loadError } = marketStore

// The primary market has no countries of its own: it takes every one no other market has.
function countriesOf(market) {
  if (market.is_primary) return markets.value.length > 1 ? __('All other countries') : __('All countries')
  return market.countries.join(', ')
}

function codeOf(market) {
  if (market.is_primary) return market.country_code
  return market.countries.length === 1 ? marketStore.countryCode(market.countries[0]) : null
}

function summaryOf(market) {
  const languages = market.languages.map(marketStore.languageName).join(', ')
  return [market.currency, countriesOf(market), languages].filter(Boolean).join(' · ')
}
</script>

<template>
  <SettingsPanelHeader :title="__('Markets')" :description="__('Sell to countries in their own currency and language.')">
    <template #actions>
      <Button
        variant="solid"
        theme="gray"
        icon-left="lucide-plus"
        :label="__('Add market')"
        :disabled="!choices"
        @click="emit('open', NEW_MARKET)"
      />
    </template>
  </SettingsPanelHeader>

  <SettingsBody v-scroll-fade>
    <EmptyState
      v-if="loadError && !markets"
      compact
      icon="lucide-triangle-alert"
      :title="__('These could not be loaded')"
      :description="__('Your storefront still sells in the markets it had.')"
    >
      <Button :label="__('Try again')" variant="subtle" theme="gray" @click="marketStore.load()" />
    </EmptyState>

    <SettingsSkeleton v-else-if="!markets || !choices" class="mt-2" :rows="3" />

    <ul v-else class="mt-2 divide-y divide-outline-gray-1 border-y border-outline-gray-1">
      <li
        v-for="market in markets"
        :key="market.handle"
        class="flex items-center gap-2 rounded-4 pe-2 hover:bg-surface-gray-1"
      >
        <!-- min-w-0: the summary line truncates instead of pushing the switch out of the row. -->
        <button
          type="button"
          class="flex min-w-0 flex-1 items-center gap-3 rounded-4 px-2 py-3 text-start"
          @click="emit('open', market.handle)"
        >
          <span
            class="grid size-8 shrink-0 place-items-center rounded-4 bg-surface-gray-2 text-xs font-medium text-ink-gray-6"
            aria-hidden="true"
          >
            <span v-if="codeOf(market)">{{ codeOf(market) }}</span>
            <span v-else class="lucide-globe size-4" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="flex items-center gap-2">
              <span class="truncate text-base font-semibold text-ink-gray-8">{{ market.market_name }}</span>
              <Badge v-if="market.is_primary" variant="subtle" theme="blue" :label="__('Primary')" />
              <Badge v-else-if="!market.enabled" variant="subtle" theme="gray" :label="__('Off')" />
            </span>
            <span class="mt-0.5 block truncate text-sm text-ink-gray-5" :title="countriesOf(market)">
              {{ summaryOf(market) }}
            </span>
          </span>
          <span class="hidden w-40 shrink-0 truncate text-end font-mono text-xs text-ink-gray-5 sm:block" dir="ltr">
            {{ urlSummary(marketStore.urlsOf(market)) }}
          </span>
          <span class="lucide-chevron-right size-4 shrink-0 text-ink-gray-4 rtl:-scale-x-100" aria-hidden="true" />
        </button>
        <span class="flex w-9 shrink-0 justify-end">
          <Switch
            v-if="!market.is_primary"
            :model-value="Boolean(market.enabled)"
            :aria-label="__('Sell in {0}', [market.market_name])"
            @update:model-value="(isOn) => marketStore.setEnabled(market, isOn)"
          />
        </span>
      </li>
    </ul>
  </SettingsBody>
</template>
