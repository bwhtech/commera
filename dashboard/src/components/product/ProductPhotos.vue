<script setup>
import { computed } from 'vue'
import VariantMedia from '../VariantMedia.vue'
import ProductSection from './ProductSection.vue'
import { productOptions } from '../../data/product'
import { __ } from '../../data/translation'

const props = defineProps({ product: { type: Object, required: true } })
const emit = defineEmits(['saved'])

// A product with no color (sizes only, or no options at all) has one placeholder variant holding
// its photos: one strip, with no row label naming the placeholder.
const hasColors = computed(() => productOptions(props.product).options.length > 0)
const isCompact = computed(() => props.product.variants.length > 1)

const hint = computed(() =>
  hasColors.value
    ? __('Each {0} has its own photos. The first one is the cover. Photos save as you add them.', [
        props.product.option_attribute.toLowerCase(),
      ])
    : __('The first photo is the cover. Photos save as you add them.'),
)
</script>

<template>
  <ProductSection id="product-photos" :title="__('Photos')" :hint="hint">
    <!-- With several colors each row is a compact strip: a drop zone per color filled the first
         phone screen. One strip keeps the large drop zone while it is empty. -->
    <!-- -mx-4 px-4 runs each row's rule over the section's px-4 to the card edges, as the Options and
         Variants rows rule, while the content keeps its inset. -->
    <div class="divide-y divide-outline-gray-1">
      <div
        v-for="variant in product.variants"
        :key="variant.name"
        class="-mx-4 flex items-start gap-3 px-4 py-3 first:pt-0 last:pb-0"
      >
        <span v-if="hasColors" class="w-20 shrink-0 truncate pt-0.5 text-base text-ink-gray-6 sm:w-24">
          {{ variant.option }}
        </span>
        <VariantMedia class="min-w-0 flex-1" :variant="variant" :compact="isCompact" @saved="emit('saved')" />
      </div>
    </div>
  </ProductSection>
</template>
