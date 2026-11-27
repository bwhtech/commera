<script setup>
import { imp } from '../../../data/importFlow'
import { __ } from '../../../data/translation'

// Shown only when ERPNext has items to bring in (see ImportDialog), so both cards are real choices.
const sources = [
  {
    value: 'csv',
    title: __('Spreadsheet'),
    body: __('A CSV or Excel file, exported from anywhere or filled in from our template.'),
    icon: 'lucide-file-spreadsheet',
  },
  {
    value: 'erpnext',
    title: 'ERPNext',
    body: __('Turn the items you already sell in ERPNext into products.'),
    icon: 'lucide-database',
  },
]
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-xl-semibold text-ink-gray-9">{{ __('Where are your products right now?') }}</h2>
      <p class="mt-1.5 text-p-base text-ink-gray-6">{{ __('You can import again later from the other one.') }}</p>
    </div>

    <div class="grid gap-4 sm:grid-cols-2">
      <button
        v-for="source in sources"
        :key="source.value"
        type="button"
        class="rounded-5 border p-5 text-start transition hover:bg-surface-gray-1"
        :class="imp.source === source.value ? 'border-outline-gray-4 bg-surface-gray-1' : 'border-outline-gray-1'"
        :aria-pressed="imp.source === source.value"
        @click="imp.source = source.value"
      >
        <div class="flex items-start gap-3">
          <span :class="[source.icon, 'size-5 shrink-0 text-ink-gray-7']" aria-hidden="true" />
          <div class="min-w-0 flex-1">
            <div class="text-base-semibold text-ink-gray-8">{{ source.title }}</div>
            <p class="mt-1 text-p-sm text-ink-gray-5">{{ source.body }}</p>
          </div>
          <!-- Always in the layout, so selecting a card never reflows its text. -->
          <span
            class="lucide-circle-check size-4 shrink-0 text-ink-green-5"
            :class="imp.source === source.value ? '' : 'invisible'"
            aria-hidden="true"
          />
        </div>
      </button>
    </div>

    <p class="text-p-sm text-ink-gray-5">{{ __('Shopify, WooCommerce and more are coming soon.') }}</p>
  </div>
</template>
