<script setup>
import { computed } from 'vue'
import VariantMedia from '../VariantMedia.vue'
import { __ } from '../../data/translation'

const props = defineProps({ product: { type: Object, required: true } })
const emit = defineEmits(['saved'])

const optionNoun = computed(() => (props.product.option_attribute ?? __('option')).toLowerCase())
</script>

<template>
  <section id="product-photos" class="rounded-5 border border-outline-gray-1">
    <div class="px-4 py-3">
      <h2 class="text-lg-semibold text-ink-gray-8">{{ __('Photos') }}</h2>
      <p class="mt-1 text-p-sm text-ink-gray-5">
        {{ __('Each {0} has its own photos. The first one is the cover.', [optionNoun]) }}
      </p>
    </div>

    <div
      v-for="variant in product.variants"
      :key="variant.name"
      class="flex flex-col gap-2 border-t border-outline-gray-1 px-4 py-3 sm:flex-row sm:items-start sm:gap-3"
    >
      <span class="shrink-0 truncate pt-0.5 text-base text-ink-gray-6 sm:w-24">{{ variant.option }}</span>
      <VariantMedia class="min-w-0 flex-1" :variant="variant" @saved="emit('saved')" />
    </div>
  </section>
</template>
