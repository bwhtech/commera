<script setup>
import { ErrorMessage } from 'frappe-ui'
import { marketStore } from '../../../data/markets'

defineProps({
  urls: { type: Array, required: true },
  error: { type: String, default: '' },
})
</script>

<template>
  <section class="space-y-3">
    <h3 class="text-base font-semibold text-ink-gray-8">{{ __('URLs') }}</h3>
    <ErrorMessage v-if="error" :message="error" />
    <ul v-if="urls.length" class="divide-y divide-outline-gray-1 border-y border-outline-gray-1">
      <li v-for="url in urls" :key="url.url" class="flex items-center gap-3 px-2 py-2">
        <span class="w-24 shrink-0 font-mono text-sm text-ink-gray-8" dir="ltr">{{ url.url }}</span>
        <!-- min-w-0: a long country name truncates instead of pushing the hreflang off the row. -->
        <span class="min-w-0 flex-1 truncate text-sm text-ink-gray-7">
          {{ marketStore.languageName(url.language) }}<template v-if="url.country"> · {{ url.country }}</template>
        </span>
        <span class="shrink-0 font-mono text-xs text-ink-gray-4" dir="ltr">hreflang {{ url.hreflang }}</span>
      </li>
    </ul>
    <p v-else class="text-p-sm text-ink-gray-5">{{ __('Pick countries and languages to see the URLs.') }}</p>
  </section>
</template>
