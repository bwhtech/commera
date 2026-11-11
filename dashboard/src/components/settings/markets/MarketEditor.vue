<script setup>
import { computed } from 'vue'
import { Alert, Badge, Button, Dropdown, FormControl, SettingsBody, Switch, dialog, toast } from 'frappe-ui'
import EmptyState from '../../EmptyState.vue'
import SettingsPanelHeader from '../SettingsPanelHeader.vue'
import MarketCountries from './MarketCountries.vue'
import MarketLanguages from './MarketLanguages.vue'
import MarketPrices from './MarketPrices.vue'
import MarketUrls from './MarketUrls.vue'
import { marketActions, marketStore } from '../../../data/markets'
import { __ } from '../../../data/translation'
import { useMarketForm } from '../../../data/useMarketForm'

const props = defineProps({
  handle: { type: String, default: null },
})

const emit = defineEmits(['back', 'created'])

const form = useMarketForm(props.handle)
const { isNew, values, errors, hasError } = form
// Same rule as make_handle() on the server, shown while the handle is empty.
const handleFromName = computed(() =>
  (values.value.market_name || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, ''),
)

// The saved record, for the header: the boxes may hold a value still on its way to the server.
const market = computed(() => (isNew ? null : marketStore.find(props.handle)))
const isPrimary = computed(() => Boolean(market.value?.is_primary))
const title = computed(() => (isNew ? __('New market') : market.value?.market_name))
const urls = computed(() => marketStore.urlsOf(values.value))
const primaryTitle = __("Your store's own market")

function saveName(name) {
  form.change('market_name', name.trim(), __('Name'))
}

async function create() {
  const handle = await form.create()
  if (handle) emit('created', handle)
}

function deleteMarket() {
  const name = market.value.market_name
  dialog.danger({
    title: __('Delete {0}?', [name]),
    message: __('Shoppers there move to the primary market. Its URLs stop working.'),
    confirmLabel: __('Delete market'),
    onConfirm: async () => {
      const { error } = await marketActions.attempt('delete_market', { handle: props.handle })
      if (error) return
      marketStore.drop(props.handle)
      emit('back')
      toast.success(__('{0} deleted', [name]))
    },
  })
}

const menu = [{ label: __('Delete market'), icon: 'lucide-trash-2', theme: 'red', onClick: deleteMarket }]
</script>

<template>
  <!-- The default slot, not #actions: frappe-ui's header drops #actions once a default slot is given. -->
  <SettingsPanelHeader>
    <div class="flex w-full min-w-0 flex-wrap items-center gap-2">
      <Button
        variant="ghost"
        icon="lucide-arrow-left rtl:-scale-x-100"
        :label="__('Back to markets')"
        @click="emit('back')"
      />
      <h2 class="min-w-0 truncate text-lg font-semibold text-ink-gray-8">{{ title }}</h2>
      <Badge v-if="isPrimary" variant="subtle" theme="blue" :label="__('Primary')" />
      <Badge v-else-if="market && !market.enabled" variant="subtle" theme="gray" :label="__('Off')" />
      <div class="ms-auto flex shrink-0 items-center gap-2">
        <template v-if="isNew">
          <Button :label="__('Cancel')" @click="emit('back')" />
          <Button
            variant="solid"
            theme="gray"
            :label="__('Create market')"
            :disabled="!form.canCreate.value"
            :loading="form.creating.value"
            @click="create"
          />
        </template>
        <Dropdown v-else-if="market && !isPrimary" :options="menu" align="end">
          <Button icon="lucide-ellipsis" :label="__('More actions')" />
        </Dropdown>
      </div>
    </div>
  </SettingsPanelHeader>

  <SettingsBody v-scroll-fade>
    <EmptyState
      v-if="!isNew && !market"
      compact
      icon="lucide-globe"
      :title="__('This market could not be opened')"
      :description="__('It may have been deleted.')"
    >
      <Button class="mt-2" :label="__('Back to markets')" @click="emit('back')" />
    </EmptyState>

    <template v-else>
      <Alert v-if="hasError" class="mb-4 !bg-surface-gray-2" theme="red" :title="__('Not saved. Fix the field below.')" />
      <Alert
        v-if="isPrimary"
        class="mb-4 !bg-surface-gray-2"
        theme="blue"
        :title="primaryTitle"
        :description="__('Edit its prices in General and its languages in Languages.')"
      />

      <div class="space-y-8 pb-8">
        <section class="space-y-4">
          <div
            v-if="market && !isPrimary"
            class="flex items-center justify-between gap-4 rounded-4 border border-outline-gray-1 px-3 py-2.5"
          >
            <p class="text-base text-ink-gray-8">{{ __('Sell in this market') }}</p>
            <Switch
              :model-value="Boolean(values.enabled)"
              :aria-label="__('Sell in this market')"
              @update:model-value="(isOn) => form.change('enabled', isOn ? 1 : 0, __('Market'))"
            />
          </div>
          <div class="grid gap-4 sm:grid-cols-2">
            <FormControl
              :label="__('Name')"
              required
              :model-value="values.market_name"
              :disabled="isPrimary"
              @update:model-value="(name) => form.set('market_name', name)"
              @change="saveName($event.target.value)"
            />
            <FormControl
              v-if="!isPrimary"
              :label="__('Handle')"
              :model-value="values.handle"
              :placeholder="isNew ? handleFromName : ''"
              :description="__('Made from the name when empty.')"
              :error="errors.handle"
              :disabled="!isNew"
              @update:model-value="(handle) => form.change('handle', handle)"
            />
          </div>
        </section>

        <MarketCountries
          :countries="values.countries"
          :handle="handle"
          :is-primary="isPrimary"
          :error="errors.countries"
          @update="(countries) => form.change('countries', countries, __('Countries'))"
        />

        <MarketLanguages
          :languages="values.languages"
          :default-language="values.default_language"
          :read-only="isPrimary"
          :error="errors.languages"
          @update:languages="form.setLanguages"
          @update:default-language="(code) => form.change('default_language', code, __('Default language'))"
        />

        <MarketPrices
          :values="values"
          :is-primary="isPrimary"
          :errors="errors"
          @change="form.change"
        />

        <MarketUrls :urls="urls" :error="errors.urls" />
      </div>
    </template>
  </SettingsBody>
</template>
