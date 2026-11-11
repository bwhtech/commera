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
  <DiscountSection :title="__('Applies to')">
    <RadioGroup v-model="discount.applies_to" :aria-label="__('Applies to')">
      <Radio value="All Products" :label="__('All products')" />
      <Radio value="Specific Products" :label="__('Specific products')" />
      <Radio value="Specific Collections" :label="__('Specific collections')" :description="__('Includes their sub-collections.')" />
      <Radio value="Specific Brands" :label="__('Specific brands')" />
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
        :label="__('Skip items already on sale')"
        :description="__('Items priced below their regular price get no extra discount.')"
      />
      <TargetPicker
        v-model="discount.targets"
        role="Excluded"
        target-type="Item"
        :label="__('Excluded products')"
        :placeholder="__('Exclude products')"
      />
    </div>
  </DiscountSection>
</template>
