<script setup>
import { ref } from 'vue'
import { Button, Dialog, FormControl, TabButtons, TextInput, toast } from 'frappe-ui'
import DiscountSection from './DiscountSection.vue'
import { codesDownloadUrl, createCodes, discountTypeLabel } from '../../data/discounts'

const discount = defineModel('discount', { type: Object, required: true })

const METHODS = [
  { label: 'Discount code', value: 'Code' },
  { label: 'Automatic', value: 'Automatic' },
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
    toast.success(`${result.created} codes created`)
    generating.value = false
  } finally {
    creatingCodes.value = false
  }
}
</script>

<template>
  <DiscountSection :title="discountTypeLabel(discount)">
    <TabButtons v-model="discount.method" size="sm" :options="METHODS" aria-label="How it applies" />

    <template v-if="discount.method === 'Code'">
      <div>
        <div class="flex items-end gap-2">
          <TextInput v-model="discount.code" class="flex-1" label="Code" placeholder="SUMMER10" />
          <Button label="Generate" @click="generateCode" />
        </div>
        <p class="mt-1.5 text-p-sm text-ink-gray-5">Shoppers type this at checkout. Matching ignores case.</p>
      </div>

      <div class="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-outline-gray-1 pt-4">
        <div class="min-w-0 flex-1">
          <p class="text-base text-ink-gray-8">Unique codes</p>
          <p class="text-p-sm text-ink-gray-5">
            <template v-if="discount.generated_codes">
              {{ discount.generated_codes_used }} of {{ discount.generated_codes }} used ·
              <a :href="codesDownloadUrl(discount.name)" class="text-ink-gray-8 underline">Download as CSV</a>
            </template>
            <template v-else-if="discount.name">Single-use codes for influencers, emails or receipts, sharing these rules.</template>
            <template v-else>Save the discount first, then generate single-use codes that share these rules.</template>
          </p>
        </div>
        <Button label="Generate codes" :disabled="!discount.name" @click="generating = true" />
      </div>
    </template>
    <FormControl
      v-else
      v-model="discount.title"
      label="Title"
      placeholder="Diwali sale"
      description="Shoppers see this in the cart and at checkout."
    />
  </DiscountSection>

  <Dialog v-model:open="generating" title="Generate unique codes" size="sm">
    <div class="space-y-4">
      <FormControl v-model="bulk.count" type="number" label="How many" description="Up to 5,000 at a time." />
      <FormControl v-model="bulk.prefix" label="Prefix" placeholder="RIYA-" description="Each code is the prefix and 8 random letters." />
    </div>
    <template #actions>
      <Button class="w-full" variant="solid" label="Generate" :loading="creatingCodes" @click="generateBulk" />
    </template>
  </Dialog>
</template>
