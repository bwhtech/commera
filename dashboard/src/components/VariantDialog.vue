<script setup>
/**
 * One variant, everything about it: its own price, stock, identifiers and
 * photos. A variant is a small record, so it opens over the product rather
 * than taking you away from the matrix you were working down.
 */
import { computed, ref, watch } from 'vue'
import { Badge, Button, Dialog, FormControl, toast } from 'frappe-ui'
import VariantMedia from './VariantMedia.vue'
import { useAdminAction, trySubmit } from '../data/api'
import { hasPrice, isPriceValid, priceFields, priceRates } from '../data/product'
import { __ } from '../data/translation'

const props = defineProps({
  variant: { type: Object, default: null },
  product: { type: Object, required: true },
})

const open = defineModel('open', { type: Boolean, default: false })
const emit = defineEmits(['saved'])

const price = ref(null)
const discountedPrice = ref(0)
// Reset on open or on a different variant only: a photo upload reloads the
// product mid-edit, and that must not wipe a price typed but not yet saved.
watch(
  [open, () => props.variant?.name],
  () => {
    if (!open.value || !props.variant) return
    const fields = priceFields(props.variant.sizes?.[0])
    price.value = fields.price
    discountedPrice.value = fields.discountedPrice ?? 0
  },
  { immediate: true },
)

// A product whose configurator is gone carries no attribute name, so the badge names the value
// on its own rather than prefixing it with nothing.
const optionLabel = computed(() =>
  props.product.option_attribute && props.variant
    ? `${props.product.option_attribute} · ${props.variant.option}`
    : (props.variant?.option ?? ''),
)

const onHand = computed(() => props.variant?.sizes?.reduce((sum, size) => sum + (size.stock ?? 0), 0) ?? 0)
const committed = computed(() => props.variant?.sizes?.reduce((sum, size) => sum + (size.committed ?? 0), 0) ?? 0)
const skuList = computed(() => props.variant?.sizes?.map((size) => size.item_code).join(', ') ?? '')

const priceAction = useAdminAction('catalog.set_variant_price')
const priceError = computed(() =>
  isPriceValid({ price: price.value, discountedPrice: discountedPrice.value })
    ? ''
    : __('Price must be higher than the discounted price.'),
)
const discountedPriceError = computed(() =>
  hasPrice(discountedPrice.value) ? '' : __('Enter a discounted price above zero.'),
)

async function save() {
  if (priceAction.loading || priceError.value || discountedPriceError.value) return
  const saved = await trySubmit(priceAction, {
    style_attribute_variant: props.variant.name,
    ...priceRates({ price: price.value, discountedPrice: discountedPrice.value }),
  })
  if (!saved) return
  open.value = false
  toast.success(__('{0} saved', [props.variant.option]))
  emit('saved')
}
</script>

<template>
  <Dialog v-model:open="open" size="2xl" :title="variant ? variant.option : __('Variant')">
    <div v-if="variant" class="space-y-6">
      <div class="flex flex-wrap items-center gap-1.5">
        <Badge :label="optionLabel" variant="subtle" />
        <span class="text-sm text-ink-gray-5">{{ __('of {0}', [product.title]) }}</span>
      </div>

      <section>
        <h3 class="text-base-semibold text-ink-gray-8">{{ __('Photos') }}</h3>
        <p class="mt-1 text-p-sm text-ink-gray-5">
          {{ __('Shown when a shopper picks this combination. The first one is the cover.') }}
        </p>
        <VariantMedia class="mt-3" :variant="variant" @saved="emit('saved')" />
      </section>

      <section>
        <h3 class="text-base-semibold text-ink-gray-8">{{ __('Pricing and stock') }}</h3>
        <p class="mt-1 text-p-sm text-ink-gray-5">
          {{ __('Applies to every size under this option ({0}).', [variant.sizes.length]) }}
        </p>
        <div class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormControl
            v-model.number="price"
            type="number"
            :label="__('Price')"
            :placeholder="__('Optional')"
            :error="priceError"
          />
          <FormControl
            v-model.number="discountedPrice"
            type="number"
            :label="`${__('Discounted price')} *`"
            :error="discountedPriceError"
          />
          <!-- Read-only: commera only exposes receiving stock (additive), not setting
               on-hand to an arbitrary number. -->
          <FormControl :model-value="String(onHand)" type="number" :label="__('On hand')" disabled />
          <FormControl :model-value="String(committed)" type="number" :label="__('Committed')" disabled />
        </div>
      </section>

      <section>
        <h3 class="text-base-semibold text-ink-gray-8">{{ __('Identifiers') }}</h3>
        <div class="mt-3">
          <!-- One SKU per size, not per option — ERPNext assigns these at
               creation and no admin endpoint renames them. -->
          <FormControl :model-value="skuList" :label="__('SKU')" disabled />
        </div>
      </section>
    </div>

    <!-- Slot omitted entirely while there is no variant, so the dialog does not
         render an empty action band over an empty body. -->
    <template v-if="variant" #actions>
      <div class="flex w-full justify-end gap-2">
        <Button :label="__('Cancel')" :disabled="priceAction.loading" @click="open = false" />
        <Button
          :label="__('Save variant')"
          variant="solid"
          theme="gray"
          :disabled="Boolean(priceError || discountedPriceError)"
          :loading="priceAction.loading"
          @click="save"
        />
      </div>
    </template>
  </Dialog>
</template>

