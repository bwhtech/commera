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
    <div class="divide-y divide-outline-gray-1">
      <div
        v-for="variant in product.variants"
        :key="variant.name"
        class="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:gap-3"
      >
        <span v-if="hasColors" class="shrink-0 truncate pt-0.5 text-base text-ink-gray-6 sm:w-24">
          {{ variant.option }}
        </span>
        <VariantMedia class="min-w-0 flex-1" :variant="variant" @saved="emit('saved')" />
      </div>
    </div>
  </ProductSection>
</template>
