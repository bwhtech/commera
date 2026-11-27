<script setup>
/**
 * One color: its price, which every size under it shares, its sizes' stock and its photos.
 */
import { computed, watch } from 'vue'
import { Button, toast } from 'frappe-ui'
import FormDialog from './FormDialog.vue'
import PriceFields from './PriceFields.vue'
import VariantMedia from './VariantMedia.vue'
import { useAdminAction, trySubmit } from '../data/api'
import { usePriceDraft } from '../data/priceDraft'
import { colorLabel, groupSizes, isSizesOnly, priceScopeHint, priceUpdatedMessage, stockRows } from '../data/variants'
import { __ } from '../data/translation'

const props = defineProps({
  variant: { type: Object, default: null },
  product: { type: Object, required: true },
})

const open = defineModel('open', { type: Boolean, default: false })
const emit = defineEmits(['saved', 'add-stock'])

const draft = usePriceDraft(() => props.variant?.sizes?.[0])
const { price, originalPrice, priceError, originalError, isChanged } = draft

// Loaded on open or for a different color only: a photo upload reloads the product mid-edit, and
// a trip to Add stock comes back here, and neither may wipe a price typed but not yet saved.
watch(
  [open, () => props.variant?.name],
  () => {
    if (open.value && props.variant) draft.start(props.variant.name)
  },
  { immediate: true },
)

const sizesOnly = computed(() => Boolean(props.variant && isSizesOnly(props.variant)))
// A sizes-only product has one hidden color, so the dialog is about the product itself.
const title = computed(() => {
  if (!props.variant) return ''
  return sizesOnly.value ? props.product.title : colorLabel(props.variant)
})
const description = computed(() => {
  if (sizesOnly.value) return __('All sizes of {0}', [props.product.title])
  return __('{0} of {1}', [props.product.option_attribute, props.product.title])
})
const priceHint = computed(() => (props.variant ? priceScopeHint(props.variant) : ''))

const sizes = computed(() => (props.variant ? groupSizes(props.variant) : []))

const blockedReason = computed(() => priceError.value || originalError.value)

const priceAction = useAdminAction('catalog.set_variant_price')

async function save() {
  if (!isChanged.value) {
    open.value = false
    return
  }
  if (priceAction.loading || blockedReason.value) return
  const saved = await trySubmit(priceAction, { style_attribute_variant: props.variant.name, ...draft.rates.value })
  if (!saved) return
  open.value = false
  toast.success(priceUpdatedMessage(props.variant))
  emit('saved')
}

// Steps out to Add stock and is reopened after it, so the price draft is held, not saved.
function addStock(rows) {
  draft.hold(props.variant.name)
  open.value = false
  emit('add-stock', rows)
}
</script>

<template>
  <FormDialog
    v-if="variant"
    v-model:open="open"
    :title="title"
    :description="description"
    :primary-label="__('Save price')"
    :primary-disabled="Boolean(isChanged && blockedReason)"
    :reason="isChanged ? blockedReason : ''"
    :loading="priceAction.loading"
    @submit="save"
  >
    <div class="space-y-6">
      <PriceFields
        v-model:price="price"
        v-model:original-price="originalPrice"
        :price-error="priceError"
        :original-price-error="originalError"
        :price-description="priceHint"
      />

      <section v-if="sizes.length">
        <div class="flex items-center justify-between gap-2">
          <h4 class="text-base-semibold text-ink-gray-8">{{ __('Sizes') }}</h4>
          <Button size="sm" icon-left="lucide-package-plus" :label="__('Add stock')" @click="addStock(stockRows([variant]))" />
        </div>
        <table class="mt-2 w-full text-start">
          <thead>
            <tr class="border-b border-outline-gray-1 text-sm text-ink-gray-5">
              <th class="py-1.5 pe-3 text-start font-normal">{{ __('Size') }}</th>
              <th class="py-1.5 text-end font-normal">{{ __('In stock') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="size in sizes" :key="size.item_code" class="border-b border-outline-gray-1 last:border-0">
              <td class="py-2 pe-3 text-base text-ink-gray-8">
                {{ size.size }}
              </td>
              <td class="py-2 text-end text-base tabular-nums text-ink-gray-8">{{ size.stock ?? 0 }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section>
        <h4 class="text-base-semibold text-ink-gray-8">{{ __('Photos') }}</h4>
        <p class="mt-1 text-p-sm text-ink-gray-5">{{ __('Photos save as you add them.') }}</p>
        <VariantMedia class="mt-3" :variant="variant" @saved="emit('saved')" />
      </section>
    </div>
  </FormDialog>
</template>
