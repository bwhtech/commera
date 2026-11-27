<script setup>
/**
 * One color: its price, which every size under it shares, its sizes' stock and its photos.
 */
import { computed, ref, watch } from 'vue'
import { Button, FormControl, toast } from 'frappe-ui'
import FormDialog from './FormDialog.vue'
import VariantMedia from './VariantMedia.vue'
import { useAdminAction, trySubmit } from '../data/api'
import { symbolFor } from '../data/format'
import { PLACEHOLDER_ATTRIBUTE, hasPrice, originalPriceError, priceInputRates, priceInputs } from '../data/product'
import { colorLabel, groupSizes, stockRows } from '../data/variants'
import { __ } from '../data/translation'

const props = defineProps({
  variant: { type: Object, default: null },
  product: { type: Object, required: true },
})

const open = defineModel('open', { type: Boolean, default: false })
const emit = defineEmits(['saved', 'add-stock'])

const price = ref(null)
const originalPrice = ref(null)
const showOriginalPrice = ref(false)
const stored = computed(() => priceInputs(props.variant?.sizes?.[0]))

// Reset on open or on a different color only: a photo upload reloads the
// product mid-edit, and that must not wipe a price typed but not yet saved.
watch(
  [open, () => props.variant?.name],
  () => {
    if (!open.value || !props.variant) return
    price.value = stored.value.price
    originalPrice.value = stored.value.originalPrice
    showOriginalPrice.value = hasPrice(stored.value.originalPrice)
  },
  { immediate: true },
)

const title = computed(() => (props.variant ? colorLabel(props.variant) : ''))
const subtitle = computed(() => {
  const option = props.product.option_attribute
  if (!option || option === PLACEHOLDER_ATTRIBUTE) return props.product.title
  return __('{0} of {1}', [option, props.product.title])
})
const priceHint = computed(() =>
  props.product.option_attribute === PLACEHOLDER_ATTRIBUTE
    ? __('Same price for every size.')
    : __('Same price for every size of {0}.', [title.value]),
)

const sizes = computed(() => (props.variant ? groupSizes(props.variant) : []))
const currency = symbolFor()

const priceError = computed(() => (hasPrice(price.value) ? '' : __('Enter a price above zero.')))
const originalError = computed(() =>
  showOriginalPrice.value ? originalPriceError({ price: price.value, originalPrice: originalPrice.value }) : '',
)
const blockedReason = computed(() => priceError.value || originalError.value)
const isChanged = computed(
  () =>
    Number(price.value) !== Number(stored.value.price) ||
    Number(showOriginalPrice.value ? originalPrice.value || 0 : 0) !== Number(stored.value.originalPrice || 0),
)

function removeOriginalPrice() {
  originalPrice.value = null
  showOriginalPrice.value = false
}

const priceAction = useAdminAction('catalog.set_variant_price')

async function save() {
  if (!isChanged.value) {
    open.value = false
    return
  }
  if (priceAction.loading || blockedReason.value) return
  const saved = await trySubmit(priceAction, {
    style_attribute_variant: props.variant.name,
    ...priceInputRates({ price: price.value, originalPrice: showOriginalPrice.value ? originalPrice.value : null }),
  })
  if (!saved) return
  open.value = false
  toast.success(__('Price updated for {0}', [title.value]))
  emit('saved')
}

function addStock(rows) {
  open.value = false
  emit('add-stock', rows)
}
</script>

<template>
  <FormDialog
    v-if="variant"
    v-model:open="open"
    :title="title"
    :primary-label="__('Save price')"
    :primary-disabled="Boolean(isChanged && blockedReason)"
    :reason="isChanged ? blockedReason : ''"
    :loading="priceAction.loading"
    @submit="save"
  >
    <div class="space-y-6">
      <p class="-mt-2 text-p-sm text-ink-gray-5">{{ subtitle }}</p>
      <section class="space-y-3">
        <FormControl
          v-model.number="price"
          type="number"
          :label="__('Price')"
          required
          :error="priceError"
          :description="priceHint"
        >
          <template #prefix><span class="text-base text-ink-gray-5">{{ currency }}</span></template>
        </FormControl>
        <div v-if="showOriginalPrice" class="flex items-start gap-2">
          <FormControl
            v-model.number="originalPrice"
            class="min-w-0 flex-1"
            type="number"
            :label="__('Original price')"
            :description="__('Shown crossed out next to the price. Must be higher than the price.')"
            :error="originalError"
          >
            <template #prefix><span class="text-base text-ink-gray-5">{{ currency }}</span></template>
          </FormControl>
          <Button class="mt-6" variant="ghost" icon="lucide-x" :label="__('Remove original price')" @click="removeOriginalPrice" />
        </div>
        <Button v-else variant="ghost" icon-left="lucide-plus" :label="__('Add original price')" @click="showOriginalPrice = true" />
      </section>

      <section v-if="sizes.length">
        <div class="flex items-center justify-between gap-2">
          <h4 class="text-base-semibold text-ink-gray-8">{{ __('Sizes') }}</h4>
          <Button size="sm" icon-left="lucide-package-plus" :label="__('Add stock')" @click="addStock(stockRows([variant]))" />
        </div>
        <table class="mt-2 w-full text-start">
          <thead>
            <tr class="border-b border-outline-gray-1 text-sm text-ink-gray-5">
              <th class="py-1.5 pe-3 text-start font-normal">{{ __('Size') }}</th>
              <th class="py-1.5 pe-3 text-end font-normal">{{ __('In stock') }}</th>
              <th class="py-1.5 text-start font-normal max-sm:hidden">{{ __('SKU') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="size in sizes" :key="size.item_code" class="border-b border-outline-gray-1 last:border-0">
              <td class="py-2 pe-3 text-base text-ink-gray-8">
                {{ size.size }}
                <span class="block truncate text-xs text-ink-gray-5 sm:hidden">{{ size.item_code }}</span>
              </td>
              <td class="py-2 pe-3 text-end text-base tabular-nums text-ink-gray-8">{{ size.stock ?? 0 }}</td>
              <td class="py-2 text-sm text-ink-gray-5 max-sm:hidden">{{ size.item_code }}</td>
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
