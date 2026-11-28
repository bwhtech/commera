<script setup>
import { FormControl } from 'frappe-ui'
import RichTextField from '../RichTextField.vue'
import ProductSection from './ProductSection.vue'

defineProps({
  draft: { type: Object, required: true },
  titleError: { type: String, default: '' },
})
</script>

<template>
  <ProductSection :title="__('Details')">
    <div class="space-y-4">
      <FormControl v-model="draft.title" :label="__('Title')" :error="titleError" required />
      <RichTextField
        v-model="draft.description"
        :label="__('Description')"
        :description="__('Shown on the product page.')"
        min-height="min-h-32"
      />
    </div>
  </ProductSection>
</template>
