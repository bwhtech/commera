<script setup>
import { computed, watch } from 'vue'
import { Checkbox, Radio, RadioGroup } from 'frappe-ui'
import DiscountSection from './DiscountSection.vue'
import TargetPicker from './TargetPicker.vue'
import { SCOPE_TARGETS, scopedTargets } from '../../data/discounts'

const discount = defineModel('discount', { type: Object, required: true })

const scope = computed(() => SCOPE_TARGETS[discount.value.applies_to])

watch(
  () => discount.value.applies_to,
  () => (discount.value.targets = scopedTargets(discount.value)),
)
</script>

<template>
  <DiscountSection title="Applies to">
    <RadioGroup v-model="discount.applies_to" aria-label="Applies to">
      <Radio value="All Products" label="All products" />
      <Radio value="Specific Products" label="Specific products" />
      <Radio value="Specific Collections" label="Specific collections" description="Includes their sub-collections." />
      <Radio value="Specific Brands" label="Specific brands" />
    </RadioGroup>

    <TargetPicker
      v-if="scope"
      :key="discount.applies_to"
      v-model="discount.targets"
      role="Applies To"
      :target-type="scope.targetType"
      :label="scope.label"
      :placeholder="scope.placeholder"
    />

    <div class="space-y-3 border-t border-outline-gray-1 pt-4">
      <Checkbox
        v-model="discount.exclude_sale_items"
        label="Skip items already on sale"
        description="Items priced below their regular price get no extra discount."
      />
      <TargetPicker
        v-model="discount.targets"
        role="Excluded"
        target-type="Item"
        label="Excluded products"
        placeholder="Exclude products"
      />
    </div>
  </DiscountSection>
</template>
