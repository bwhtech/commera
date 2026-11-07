<script setup>
import { useRouter } from 'vue-router'
import { Badge } from 'frappe-ui'
import { closeImport, imp } from '../../../data/importFlow'
import CoachTip from '../CoachTip.vue'

const router = useRouter()

// The spreadsheet runs in this dialog. Shopify brings the whole store over (collections,
// customers, pages), not only products, so it has its own page. The rest are named anyway: a
// merchant should see that we know about them, and that they are not their route in yet.
const sources = [
  {
    value: 'csv',
    title: 'Spreadsheet',
    body: 'CSV or Excel exported from anywhere.',
    icon: 'lucide-file-spreadsheet',
    tag: 'Most common',
  },
  {
    value: 'shopify',
    title: 'Shopify',
    body: 'Connect your store and bring products, collections, customers and pages over.',
    icon: 'lucide-shopping-bag',
    route: { name: 'ShopifyImport' },
  },
  { value: 'woo', title: 'WooCommerce', body: 'Connect with your store URL and a key.', icon: 'lucide-plug-zap', soon: true },
  { value: 'sheets', title: 'Google Sheet', body: 'Paste a link and we keep it in sync.', icon: 'lucide-table', soon: true },
  { value: 'insta', title: 'Instagram catalogue', body: 'Bring across the products you tag in posts.', icon: 'lucide-camera', soon: true },
  { value: 'manual', title: 'Type them in', body: 'Fine for a handful of products.', icon: 'lucide-pencil-line', soon: true },
]

function choose(source) {
  if (!source.route) {
    imp.source = source.value
    return
  }
  closeImport()
  router.push(source.route)
}
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-xl text-ink-gray-9">Where are your products right now?</h2>
      <p class="mt-1.5 text-p-base text-ink-gray-6">
        Pick the one closest to your setup. You can import again later from anywhere else.
      </p>
    </div>

    <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <button
        v-for="s in sources"
        :key="s.value"
        type="button"
        class="rounded-5 border p-5 text-left transition"
        :class="[
          imp.source === s.value ? 'border-outline-gray-4 bg-surface-gray-1' : 'border-outline-gray-1',
          s.soon ? 'cursor-not-allowed opacity-60' : 'hover:bg-surface-gray-1',
        ]"
        :disabled="s.soon"
        @click="choose(s)"
      >
        <div class="flex items-start gap-3">
          <span :class="[s.icon, 'size-5 shrink-0 text-ink-gray-7']" aria-hidden="true" />
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span class="text-base-semibold text-ink-gray-8">{{ s.title }}</span>
              <Badge v-if="s.tag" class="shrink-0" :label="s.tag" theme="blue" variant="subtle" />
              <Badge v-if="s.soon" class="shrink-0" label="Coming soon" theme="gray" variant="subtle" />
            </div>
            <p class="mt-1 text-p-sm text-ink-gray-5">{{ s.body }}</p>
          </div>
          <!-- Always in the layout, so selecting a card never reflows its text. -->
          <span
            class="lucide-circle-check size-4 shrink-0 text-ink-green-5"
            :class="imp.source === s.value ? '' : 'invisible'"
            aria-hidden="true"
          />
        </div>
      </button>
    </div>

    <CoachTip
      title="Not sure which one to pick?"
      text="Export a CSV from your old store and choose Spreadsheet. Every platform can produce one, and it carries your prices and stock counts along."
    />
  </div>
</template>

