<script setup>
import { Checkbox, Radio, RadioGroup } from 'frappe-ui'
import DiscountSection from './DiscountSection.vue'
import TargetPicker from './TargetPicker.vue'

const discount = defineModel('discount', { type: Object, required: true })

const TARGET_TYPE_BY_SCOPE = {
  'Specific Products': { targetType: 'Item', placeholder: 'Search products' },
  'Specific Collections': { targetType: 'Item Group', placeholder: 'Search collections' },
  'Specific Brands': { targetType: 'Brand', placeholder: 'Search brands' },
}
</script>

<template>
  <DiscountSection title="Applies to">
    <RadioGroup v-model="discount.applies_to">
      <Radio value="All Products" label="All products" />
      <Radio value="Specific Products" label="Specific products" />
      <Radio value="Specific Collections" label="Specific collections" description="Includes their sub-collections." />
      <Radio value="Specific Brands" label="Specific brands" />
    </RadioGroup>

    <TargetPicker
      v-if="TARGET_TYPE_BY_SCOPE[discount.applies_to]"
      :key="discount.applies_to"
      v-model="discount.targets"
      role="Applies To"
      :target-type="TARGET_TYPE_BY_SCOPE[discount.applies_to].targetType"
      :placeholder="TARGET_TYPE_BY_SCOPE[discount.applies_to].placeholder"
    />

    <div class="space-y-3 border-t border-outline-gray-1 pt-4">
      <Checkbox
        v-model="discount.exclude_sale_items"
        label="Skip items already on sale"
        description="Items priced below their regular price get no extra discount."
      />
      <TargetPicker v-model="discount.targets" role="Excluded" target-type="Item" placeholder="Exclude products" />
    </div>
  </DiscountSection>
</template>
