<script setup>
/**
 * One variant, everything about it: its own price, stock, identifiers and
 * photos. A variant is a small record, so it opens over the product rather
 * than taking you away from the matrix you were working down.
 */
import { computed, ref, watch } from 'vue'
import { Badge, Button, Dialog, FormControl, toast } from 'frappe-ui'
import VariantMedia from './VariantMedia.vue'
import { useAdminAction } from '../data/api'
import { pricePayload, shownPrice } from '../data/product'
import { productRoute } from '../ia/routes'

const props = defineProps({
  variant: { type: Object, default: null },
  product: { type: Object, required: true },
})

const open = defineModel('open', { type: Boolean, default: false })
const emit = defineEmits(['saved'])

// Bulk price editing across every size under this option — the same call
// the product page's matrix row uses (catalog.set_variant_price). Price is
// what a shopper is charged (shownPrice in data/product.js); Compare-at is
// the default price list, shown raw rather than through compareAtPrice so
// that a reference equal to the price still round-trips through the box
// instead of being erased by a save that only meant to change the price.
const price = ref(0)
const compareAt = ref(null)
// Reset on open or on a different variant only: a photo upload reloads the
// product mid-edit, and that must not wipe a price typed but not yet saved.
watch(
  [open, () => props.variant?.name],
  () => {
    if (!open.value || !props.variant) return
    const first = props.variant.sizes?.[0]
    compareAt.value = first?.default_rate ?? null
    price.value = shownPrice(first)
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

async function save() {
  const hasCompareAt = compareAt.value != null && compareAt.value !== ''
  // With no compare-at there is only one price to write, and it has to land on the list already
  // in force: a product created without one is priced on the sale list alone, so writing the
  // default list there would leave the shopper paying the old rate.
  try {
    await priceAction.submit({
      style_attribute_variant: props.variant.name,
      ...(hasCompareAt
        ? { default_rate: compareAt.value, sale_rate: price.value }
        : pricePayload(props.variant.sizes?.[0], price.value)),
    })
  } catch {
    return
  }
  open.value = false
  toast.success(`${props.variant.option} saved`)
  emit('saved')
}
</script>

<template>
  <Dialog v-model:open="open" size="2xl" :title="variant ? variant.option : 'Variant'">
    <div v-if="variant" class="space-y-6">
      <div class="flex flex-wrap items-center gap-1.5">
        <Badge :label="optionLabel" variant="subtle" />
        <span class="text-sm text-ink-gray-5">of {{ product.title }}</span>
      </div>

      <section>
        <h3 class="text-base-semibold text-ink-gray-8">Photos</h3>
        <p class="mt-1 text-p-sm text-ink-gray-5">
          Shown when a shopper picks this combination. The first one is the cover.
        </p>
        <VariantMedia class="mt-3" :variant="variant" @saved="emit('saved')" />
      </section>

      <section>
        <h3 class="text-base-semibold text-ink-gray-8">Pricing and stock</h3>
        <p class="mt-1 text-p-sm text-ink-gray-5">
          Applies to every size under this option ({{ variant.sizes.length }}). Edit one size at a
          time from the variant's own page.
        </p>
        <div class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormControl v-model.number="price" type="number" label="Price" />
          <FormControl v-model.number="compareAt" type="number" label="Compare at" />
          <!-- Read-only: commera only exposes receiving stock (additive), not setting
               on-hand to an arbitrary number. -->
          <FormControl :model-value="String(onHand)" type="number" label="On hand" disabled />
          <FormControl :model-value="String(committed)" type="number" label="Committed" disabled />
        </div>
      </section>

      <section>
        <h3 class="text-base-semibold text-ink-gray-8">Identifiers</h3>
        <div class="mt-3">
          <!-- One SKU per size, not per option — ERPNext assigns these at
               creation and no admin endpoint renames them. -->
          <FormControl :model-value="skuList" label="SKU" disabled />
        </div>
      </section>
    </div>

    <!-- Slot omitted entirely while there is no variant, so the dialog does not
         render an empty action band over an empty body. -->
    <template v-if="variant" #actions>
      <div class="flex w-full items-center justify-between gap-2">
        <Button
          label="Open full page"
          icon-left="lucide-external-link"
          :route="productRoute(product.id, variant.name)"
        />
        <div class="flex gap-2">
          <Button label="Cancel" @click="open = false" />
          <Button label="Save variant" variant="solid" theme="gray" @click="save" />
        </div>
      </div>
    </template>
  </Dialog>
</template>

