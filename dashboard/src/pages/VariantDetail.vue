<script setup>
import { computed, reactive, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Button, FormControl, Skeleton, Switch, TextInput, toast } from 'frappe-ui'
import AppPageHeader from '../components/AppPageHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import PageBody from '../components/PageBody.vue'
import Thumb from '../components/Thumb.vue'
import VariantMedia from '../components/VariantMedia.vue'
import { useAdminRead, useAdminAction } from '../data/api'
import { errorMessage } from '../data/errors'
import { pricePayload, shownPrice } from '../data/product'

const route = useRoute()

const productRequest = useAdminRead('catalog.get_product', {
  params: () => ({ item_template: route.params.id }),
  refetch: true,
})

const product = computed(() => productRequest.data)
const variant = computed(() =>
  product.value?.variants.find((v) => v.name === route.params.variantId) ?? null,
)

// One draft row per size — this is the fine-grained editor (the product
// page's matrix row only offers one bulk price for every size at once).
// Price is what a shopper is charged (shownPrice in data/product.js);
// Compare at is the default price list, held raw so a reference equal to
// the price still round-trips instead of being erased on save.
const sizeDrafts = reactive({})
watch(
  variant,
  (value) => {
    for (const key of Object.keys(sizeDrafts)) delete sizeDrafts[key]
    if (!value) return
    for (const size of value.sizes) {
      sizeDrafts[size.item_code] = {
        price: shownPrice(size),
        compareAt: size.default_rate ?? null,
        receiveQty: '',
      }
    }
  },
  { immediate: true },
)

const priceAction = useAdminAction('catalog.save_product_prices')
const stockAction = useAdminAction('catalog.receive_product_stock')
const publishAction = useAdminAction('catalog.set_variant_published')

async function save() {
  const size_prices = variant.value.sizes.map((size) => {
    const draft = sizeDrafts[size.item_code]
    const hasCompareAt = draft.compareAt != null && draft.compareAt !== ''
    // With no compare-at there is only one price to write, and it has to land on the list
    // already in force — see pricePayload.
    return {
      item_code: size.item_code,
      ...(hasCompareAt
        ? { default_rate: draft.compareAt, sale_rate: draft.price }
        : pricePayload(size, draft.price)),
    }
  })
  await priceAction.submit({ style_attribute_variant: variant.value.name, size_prices })
  if (priceAction.error) return

  const received_quantities = Object.fromEntries(
    Object.entries(sizeDrafts)
      .filter(([, draft]) => Number(draft.receiveQty) > 0)
      .map(([item_code, draft]) => [item_code, Number(draft.receiveQty)]),
  )
  if (Object.keys(received_quantities).length) {
    await stockAction.submit({ style_attribute_variant: variant.value.name, received_quantities })
    if (stockAction.error) return
  }

  toast.success('Variant saved')
  productRequest.reload()
}

async function togglePublish() {
  await publishAction.submit({ style_attribute_variant: variant.value.name, publish: !variant.value.is_published })
  if (publishAction.error) return
  productRequest.reload()
}

// Two identifiers, so three ways to end up with nothing: the product read was
// refused, the product is gone, or the product loaded fine and carries no option
// by this variantId. The last one never touches the request's error and used to
// leave the screen blank forever, so it gets its own message and its own way
// back — to the product, not to the whole catalogue. §2: the error is read here
// only to word the page; useAdminRead already toasted it.
const loadFailure = computed(() => {
  if (productRequest.error) {
    return {
      icon: 'lucide-triangle-alert',
      title: 'Could not load this variant',
      description: errorMessage(productRequest.error),
      backLabel: 'Back to products',
      backRoute: '/products',
    }
  }
  if (product.value) {
    return {
      icon: 'lucide-search-x',
      title: 'Variant not found',
      description: `${product.value.title} has no option ${route.params.variantId}. It may have been deleted.`,
      backLabel: 'Back to product',
      backRoute: `/products/${product.value.name}`,
    }
  }
  return {
    icon: 'lucide-search-x',
    title: 'Product not found',
    description: `No product matches ${route.params.id}. It may have been deleted or renamed.`,
    backLabel: 'Back to products',
    backRoute: '/products',
  }
})
</script>

<template>
  <template v-if="product && variant">
    <AppPageHeader
      :title="variant.option"
      :back-to="`/products/${product.name}`"
      :breadcrumbs="[
        { label: 'Products', route: '/products' },
        { label: product.title, route: `/products/${product.name}` },
        { label: variant.option },
      ]"
    >
      <template #actions>
        <Button label="Save" variant="solid" theme="gray" @click="save" />
      </template>
    </AppPageHeader>

    <PageBody width="narrow">
      <div class="flex items-center gap-3">
        <Thumb :image="variant.images[0]" size="size-16" />
        <div>
          <p class="text-base text-ink-gray-8">{{ product.title }}</p>
          <p class="mt-1 text-sm text-ink-gray-5">{{ variant.option }}</p>
        </div>
      </div>

      <div class="mt-8 space-y-11">
        <section>
          <div class="flex items-start justify-between gap-4">
            <div>
              <h2 class="text-lg-semibold text-ink-gray-8">Published</h2>
              <p class="mt-1 text-p-sm text-ink-gray-5">
                Visible on the storefront to shoppers.
                <span v-if="variant.blockers.length" class="text-ink-amber-7">
                  {{ variant.blockers.join(' · ') }}
                </span>
              </p>
            </div>
            <!-- Disabled up front with the reason, rather than surprising the
                 owner with an error after they flip it — the rule this switch
                 enforces is Style Attribute Variant.unpublish_if_incomplete_data. -->
            <Switch
              :model-value="variant.is_published"
              :disabled="!variant.is_published && variant.blockers.length > 0"
              @update:model-value="togglePublish"
            />
          </div>
        </section>

        <section>
          <h2 class="text-lg-semibold text-ink-gray-8">Photos</h2>
          <p class="mt-1 text-p-sm text-ink-gray-5">
            Shown when a shopper picks this combination. The first one is the cover.
          </p>
          <VariantMedia class="mt-4" :variant="variant" @saved="productRequest.reload()" />
        </section>

        <section>
          <h2 class="text-lg-semibold text-ink-gray-8">Options</h2>
          <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <!-- Read-only: this value is set at creation (ERPNext's variant
                 attributes) and renaming it here has no supported endpoint —
                 it would also silently break the option's existing route,
                 prices and stock, all keyed off it. -->
            <FormControl :model-value="variant.option" class="w-full" :label="product.option_attribute" disabled />
          </div>
        </section>

        <section v-for="size in variant.sizes" :key="size.item_code">
          <h2 class="text-lg-semibold text-ink-gray-8">Size {{ size.size }}</h2>
          <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormControl v-model.number="sizeDrafts[size.item_code].price" type="number" label="Price" />
            <FormControl v-model.number="sizeDrafts[size.item_code].compareAt" type="number" label="Compare at" />
            <FormControl :model-value="size.item_code" label="SKU" disabled />
            <!-- No barcode field surfaced by the admin API. -->
            <FormControl model-value="" label="Barcode" disabled />
          </div>
          <div class="mt-4 flex items-center justify-between rounded-4 border border-outline-gray-1 px-4 py-3">
            <span class="text-base text-ink-gray-7">On hand: {{ size.stock }} · Committed: {{ size.committed }}</span>
            <!-- commera only exposes receiving stock in (Style Attribute
                 Variant.receive_stock, additive) — there is no "set to X"
                 adjustment, so this is a quantity to add on Save, not the new total. -->
            <TextInput
              v-model="sizeDrafts[size.item_code].receiveQty"
              type="number"
              size="sm"
              class="w-28"
              placeholder="Receive qty"
            />
          </div>
        </section>

        <EmptyState
          v-if="!variant.sizes.length"
          compact
          icon="lucide-ruler"
          title="No sizes yet"
          description="Add a size so this variant can be stocked and sold."
        />
      </div>
    </PageBody>
  </template>

  <!-- The route already carries both identifiers, so the header and the shape of
       the page are drawn from them and only the values wait on the request. -->
  <template v-else-if="productRequest.loading">
    <AppPageHeader
      :title="route.params.variantId"
      :back-to="`/products/${route.params.id}`"
      :breadcrumbs="[
        { label: 'Products', route: '/products' },
        { label: route.params.id, route: `/products/${route.params.id}` },
        { label: route.params.variantId },
      ]"
    />

    <PageBody width="narrow">
      <div class="flex items-center gap-3">
        <Skeleton class="size-16 rounded-4" />
        <div class="space-y-2">
          <Skeleton class="h-4 w-40 rounded" />
          <Skeleton class="h-3.5 w-24 rounded" />
        </div>
      </div>

      <div class="mt-8 space-y-11">
        <section v-for="placeholder in 3" :key="placeholder">
          <Skeleton class="h-5 w-32 rounded" />
          <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Skeleton class="h-8 rounded" />
            <Skeleton class="h-8 rounded" />
          </div>
        </section>
      </div>
    </PageBody>
  </template>

  <!-- The request has settled with nothing to show. Without this branch a bad id,
       an unknown variantId or a refusal paints an empty screen. -->
  <template v-else>
    <AppPageHeader
      :title="route.params.variantId"
      :back-to="`/products/${route.params.id}`"
      :breadcrumbs="[
        { label: 'Products', route: '/products' },
        { label: route.params.id, route: `/products/${route.params.id}` },
        { label: route.params.variantId },
      ]"
    />

    <PageBody width="narrow">
      <EmptyState
        :icon="loadFailure.icon"
        :title="loadFailure.title"
        :description="loadFailure.description"
      >
        <Button :label="loadFailure.backLabel" variant="subtle" theme="gray" :route="loadFailure.backRoute" />
      </EmptyState>
    </PageBody>
  </template>
</template>

