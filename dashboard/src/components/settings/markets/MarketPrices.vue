<script setup>
import { computed } from 'vue'
import { FormControl } from 'frappe-ui'
import { marketStore } from '../../../data/markets'
import { __ } from '../../../data/translation'

const props = defineProps({
  values: { type: Object, required: true },
  isPrimary: { type: Boolean, default: false },
  errors: { type: Object, required: true },
})

const emit = defineEmits(['change'])

const choices = computed(() => marketStore.choices.value)

function priceListOptions(selected) {
  const priceLists = choices.value?.price_lists ?? []
  const options = priceLists.map(({ name, currency }) => ({ label: `${name} (${currency})`, value: name }))
  // The primary market's lists come from General and may be off the selling list here.
  if (selected && !priceLists.some(({ name }) => name === selected)) options.unshift({ label: selected, value: selected })
  return options
}

const saleOptions = computed(() => priceListOptions(props.values.sale_price_list))
const compareAtOptions = computed(() => [
  { label: __('None'), value: '' },
  ...priceListOptions(props.values.compare_at_price_list),
])

// Null until Commera Market has the field: the select is not drawn at all.
const taxTemplates = computed(() => (props.isPrimary ? null : choices.value?.tax_templates))
const taxOptions = computed(() => [
  { label: __('Store default'), value: '' },
  ...taxTemplates.value.map((name) => ({ label: name, value: name })),
])

const currency = computed(() => marketStore.currencyOf(props.values.sale_price_list) || props.values.currency)
</script>

<template>
  <section class="space-y-4">
    <h3 class="text-base font-semibold text-ink-gray-8">{{ __('Prices and taxes') }}</h3>
    <div class="grid gap-4 sm:grid-cols-2">
      <FormControl
        type="select"
        :label="__('Sale price list')"
        required
        :model-value="values.sale_price_list"
        :options="saleOptions"
        :placeholder="__('Choose a price list')"
        :disabled="isPrimary"
        :error="errors.sale_price_list"
        @update:model-value="(name) => emit('change', 'sale_price_list', name, __('Sale price list'))"
      />
      <FormControl
        type="select"
        :label="__('Compare-at price list')"
        :description="__('Shown struck through.')"
        :model-value="values.compare_at_price_list ?? ''"
        :options="compareAtOptions"
        :disabled="isPrimary"
        :error="errors.compare_at_price_list"
        @update:model-value="(name) => emit('change', 'compare_at_price_list', name ?? '', __('Compare-at price list'))"
      />
      <div>
        <p class="text-sm text-ink-gray-6">{{ __('Currency') }}</p>
        <p class="mt-1.5 text-base text-ink-gray-8">{{ currency || '—' }}</p>
        <p class="mt-1 text-p-xs text-ink-gray-5">{{ __('From the sale price list.') }}</p>
      </div>
      <FormControl
        v-if="taxTemplates"
        type="select"
        :label="__('Tax template')"
        :model-value="values.tax_template ?? ''"
        :options="taxOptions"
        :error="errors.tax_template"
        @update:model-value="(name) => emit('change', 'tax_template', name ?? '', __('Tax template'))"
      />
    </div>
    <p v-if="!isPrimary" class="text-p-sm text-ink-gray-5">
      {{
        values.sale_price_list
          ? __('Products without a price in {0} are not sold here.', [values.sale_price_list])
          : __('Products without a price in the sale price list are not sold here.')
      }}
    </p>
  </section>
</template>
