<script setup>
import { FormControl } from 'frappe-ui'

defineProps({ product: { type: Object, required: true } })
</script>

<template>
  <section>
    <h2 class="text-lg-semibold text-ink-gray-8">{{ __('Pricing') }}</h2>
    <p v-if="product.hasVariants" class="mt-1 text-p-sm text-ink-gray-5">
      {{ __('This product has variants. Price is set per variant below.') }}
    </p>
    <!-- Dead in practice: every real commera product goes through a Style
         Attribute Configurator, so hasVariants is always true. Kept for the
         mock's variant-less products, but its Cost field has no real field
         to bind to either way — confirmed absent from commera entirely
         the 55% here was always a client-side
         guess, never a stored value. -->
    <div v-else class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
      <FormControl :model-value="String(product.price)" type="number" :label="__('Price')" />
      <FormControl :model-value="product.compareAt ? String(product.compareAt) : ''" type="number" :label="__('Compare at')" />
      <FormControl
        :model-value="String(Math.round(product.price * 0.55))"
        type="number"
        :label="__('Cost')"
        :description="__('Not shown to customers.')"
      />
    </div>
  </section>
</template>
