<script setup>
import { computed } from 'vue'
import { Button } from 'frappe-ui'
import ProductSection from './ProductSection.vue'
import { copyProductLink, storefrontUrl } from '../../ia/productActions'
import { __ } from '../../data/translation'

const props = defineProps({
  product: { type: Object, required: true },
  isLive: { type: Boolean, required: true },
})

const url = computed(() => storefrontUrl(props.product))

const hint = computed(() => {
  if (props.product.status === 'archived') return __('Archived. Shoppers cannot see this product.')
  if (props.isLive) return __('Live. Shoppers can find and buy this product.')
  return __('Draft. Shoppers cannot see this product until you publish it.')
})
</script>

<template>
  <ProductSection id="product-storefront" :title="__('On your store')" :hint="hint">
    <template v-if="url" #actions>
      <Button :label="__('Copy link')" icon-left="lucide-link" @click="copyProductLink(url)" />
      <Button
        :label="isLive ? __('View on store') : __('Preview')"
        icon-right="lucide-external-link"
        :href="url"
      />
    </template>
  </ProductSection>
</template>
