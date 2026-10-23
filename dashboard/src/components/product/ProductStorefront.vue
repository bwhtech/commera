<script setup>
import { computed } from 'vue'
import { Badge, Button } from 'frappe-ui'

const props = defineProps({ product: { type: Object, required: true } })

// The storefront address belongs to the option, not the product: each
// colour is its own page, and Style Attribute Variant.route is generated
// server-side from its name. There is nothing to type here.
const listings = computed(() => props.product.variants.filter((variant) => variant.storefront_url))
</script>

<template>
  <section id="product-storefront">
    <h2 class="text-lg-semibold text-ink-gray-8">Storefront listing</h2>
    <p class="mt-1 text-p-sm text-ink-gray-5">
      Every option has its own page on the store. These are the live addresses.
    </p>

    <div
      v-if="listings.length"
      class="mt-4 divide-y divide-outline-gray-1 rounded-5 border border-outline-gray-1"
    >
      <div v-for="variant in listings" :key="variant.name" class="flex items-center gap-3 px-4 py-3">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="text-base text-ink-gray-8">{{ variant.option }}</span>
            <Badge v-if="!variant.is_published" label="Not published" theme="amber" variant="subtle" />
          </div>
          <p class="mt-0.5 truncate text-sm text-ink-gray-5">{{ variant.storefront_url }}</p>
        </div>
        <Button label="Open" icon-right="lucide-external-link" :href="variant.storefront_url" />
      </div>
    </div>

    <p v-else class="mt-4 text-p-base text-ink-gray-5">
      No option has a storefront address yet. One is generated when an option is first saved.
    </p>
  </section>
</template>
