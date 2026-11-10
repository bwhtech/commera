<script setup>
import { ref } from 'vue'
import { Button, Dialog, FormControl, TabButtons, TextInput, toast } from 'frappe-ui'
import DiscountSection from './DiscountSection.vue'
import { codesDownloadUrl, createCodes, discountTypeLabel } from '../../data/discounts'
import { __ } from '../../data/translation'

const discount = defineModel('discount', { type: Object, required: true })

const METHODS = [
  { label: __('Discount code'), value: 'Code' },
  { label: __('Automatic'), value: 'Automatic' },
]
const CODE_LETTERS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'

function generateCode() {
  const randomValues = crypto.getRandomValues(new Uint32Array(8))
  discount.value.code = Array.from(randomValues, (value) => CODE_LETTERS[value % CODE_LETTERS.length]).join('')
}

const generating = ref(false)
const bulk = ref({ count: 100, prefix: '' })
const creatingCodes = ref(false)

async function generateBulk() {
  creatingCodes.value = true
  try {
    const result = await createCodes(discount.value.name, bulk.value.count, bulk.value.prefix)
    if (!result) return
    discount.value.generated_codes = Number(discount.value.generated_codes ?? 0) + result.created
    toast.success(__('{0} codes created', [result.created]))
    generating.value = false
  } finally {
    creatingCodes.value = false
  }
}
</script>

<template>
  <DiscountSection :title="discountTypeLabel(discount)">
    <TabButtons v-model="discount.method" size="sm" :options="METHODS" :aria-label="__('How it applies')" />

    <template v-if="discount.method === 'Code'">
      <div>
        <div class="flex items-end gap-2">
          <TextInput v-model="discount.code" class="flex-1" :label="__('Code')" placeholder="SUMMER10" />
          <Button :label="__('Generate')" @click="generateCode" />
        </div>
        <p class="mt-1.5 text-p-sm text-ink-gray-5">{{ __('Shoppers type this at checkout. Matching ignores case.') }}</p>
      </div>

      <div class="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-outline-gray-1 pt-4">
        <div class="min-w-0 flex-1">
          <p class="text-base text-ink-gray-8">{{ __('Unique codes') }}</p>
          <p class="text-p-sm text-ink-gray-5">
            <template v-if="discount.generated_codes">
              {{ __('{0} of {1} used', [discount.generated_codes_used, discount.generated_codes]) }} ·
              <a :href="codesDownloadUrl(discount.name)" class="text-ink-gray-8 underline">{{ __('Download as CSV') }}</a>
            </template>
            <template v-else-if="discount.name">{{ __('Single-use codes for influencers, emails or receipts, sharing these rules.') }}</template>
            <template v-else>{{ __('Save the discount first, then generate single-use codes that share these rules.') }}</template>
          </p>
        </div>
        <Button :label="__('Generate codes')" :disabled="!discount.name" @click="generating = true" />
      </div>
    </template>
    <FormControl
      v-else
      v-model="discount.title"
      :label="__('Title')"
      :placeholder="__('Diwali sale')"
      :description="__('Shoppers see this in the cart and at checkout.')"
    />
  </DiscountSection>

  <Dialog v-model:open="generating" :title="__('Generate unique codes')" size="sm">
    <div class="space-y-4">
      <FormControl v-model="bulk.count" type="number" :label="__('How many')" :description="__('Up to 5,000 at a time.')" />
      <FormControl v-model="bulk.prefix" :label="__('Prefix')" placeholder="RIYA-" :description="__('Each code is the prefix and 8 random letters.')" />
    </div>
    <template #actions>
      <Button class="w-full" variant="solid" :label="__('Generate')" :loading="creatingCodes" @click="generateBulk" />
    </template>
  </Dialog>
</template>
