<script setup>
import { computed, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { useEventListener, useMediaQuery } from '@vueuse/core'
import { Breadcrumbs, Button, Dropdown, ScrollArea, Skeleton, toast } from 'frappe-ui'
import AppPageHeader from '../components/AppPageHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import PageBody from '../components/PageBody.vue'
import StatusBadge from '../components/StatusBadge.vue'
import VariantEditor from '../components/VariantEditor.vue'
import ProductBasics from '../components/product/ProductBasics.vue'
import ProductPhotos from '../components/product/ProductPhotos.vue'
import ProductPricing from '../components/product/ProductPricing.vue'
import ProductOrganization from '../components/product/ProductOrganization.vue'
import ProductStorefront from '../components/product/ProductStorefront.vue'
import ProductSummaryPanel from '../components/product/ProductSummaryPanel.vue'
import PluginActionDialog from '../components/PluginActionDialog.vue'
import PluginSlot from '../components/PluginSlot.vue'
import { useAdminRead, useAdminAction, trySubmit } from '../data/api'
import { errorMessage } from '../data/errors'
import { priceRange } from '../data/format'
import { hasPrice, originalPriceError, priceInputRates, priceInputs, productOptions, useProductStats } from '../data/product'
import { changedFields, rebaseDraft, storedDraft } from '../data/productDraft'
import { useRecordPlugins } from '../data/recordPlugins'
import { __ } from '../data/translation'
import { confirmLeave } from '../utils/confirmLeave'
import { useIsMobile } from '../utils/useIsMobile'
import { asDropdownOptions, buildProductActions } from '../ia/productActions'

const route = useRoute()
const router = useRouter()

const productRequest = useAdminRead('catalog.get_product', {
  params: () => ({ item_template: route.params.id }),
  refetch: true,
})

// The server's answer only. What the merchant is typing lives in `draft` below, so the reload
// every photo, option, price and stock write triggers can never overwrite it.
const product = computed(() => {
  const data = productRequest.data
  if (!data) return null
  const isLive = data.variants.some((variant) => variant.is_published)
  return {
    id: data.name,
    title: data.title,
    description: data.description,
    collections: data.collections,
    status: data.disabled ? 'archived' : isLive ? 'live' : 'draft',
    restock_level: data.restock_level,
    variants: data.variants,
    option_attribute: data.option_attribute,
    can_edit_options: data.can_edit_options,
    recent_sales: data.recent_sales,
  }
})

const isLive = computed(() => product.value?.status === 'live')
const stats = useProductStats(product)

// No color and no size: the product sells as one item, so its price and stock are edited on the
// page instead of through a variant named after the placeholder.
function isSingleItem(data) {
  const { options, sizes } = productOptions(data)
  return !options.length && !sizes.length && data.variants.length === 1 && data.variants[0].sizes.length === 1
}

const singleItem = computed(() => (product.value && isSingleItem(product.value) ? product.value.variants[0] : null))

const BASIC_FIELDS = ['title', 'description', 'collections']
const PRICE_FIELDS = ['price', 'originalPrice']

function storedValues(data) {
  if (!isSingleItem(data)) return storedDraft(data, BASIC_FIELDS)
  return storedDraft({ ...data, ...priceInputs(data.variants[0].sizes[0]) }, [...BASIC_FIELDS, ...PRICE_FIELDS])
}

const stored = ref(null)
const draft = ref(null)
const draftProductId = ref(null)

watch(
  () => productRequest.data,
  (data) => {
    if (!data) return
    const next = storedValues(data)
    if (draftProductId.value === data.name) {
      draft.value = rebaseDraft(draft.value, stored.value, next)
    } else {
      draft.value = storedDraft(next, Object.keys(next))
      draftProductId.value = data.name
    }
    stored.value = next
  },
  { immediate: true },
)

const changed = computed(() => (draft.value ? changedFields(draft.value, stored.value) : []))
const isDirty = computed(() => changed.value.length > 0)

const titleError = computed(() => (draft.value?.title.trim() ? '' : __('Enter a title.')))
const priceError = computed(() =>
  changed.value.includes('price') && !hasPrice(draft.value.price) ? __('Enter a price above zero.') : '',
)
const originalPriceMessage = computed(() =>
  changed.value.some((field) => PRICE_FIELDS.includes(field)) ? originalPriceError(draft.value) : '',
)
const hasErrors = computed(() => Boolean(titleError.value || priceError.value || originalPriceMessage.value))

const updateAction = useAdminAction('catalog.update_product')
const priceAction = useAdminAction('catalog.set_variant_price')
const publishAction = useAdminAction('catalog.set_product_published')
const saving = ref(false)

// Writes only the fields that changed. The prices go first: a refused price must not leave the
// title saved and the merchant unsure which half went through.
async function save() {
  if (!isDirty.value || hasErrors.value || saving.value) return
  const submitted = { ...draft.value }
  const fields = changed.value
  const basics = fields.filter((field) => BASIC_FIELDS.includes(field))
  saving.value = true
  const savedFields = []
  try {
    if (fields.some((field) => PRICE_FIELDS.includes(field))) {
      const priced = await trySubmit(priceAction, {
        style_attribute_variant: singleItem.value.name,
        ...priceInputRates(submitted),
      })
      if (!priced) return
      savedFields.push(...PRICE_FIELDS)
    }
    if (basics.length) {
      const updated = await trySubmit(updateAction, {
        item_template: product.value.id,
        ...Object.fromEntries(basics.map((field) => [field, submitted[field]])),
      })
      if (!updated) return
      savedFields.push(...basics)
    }
    toast.success(__('Saved'))
  } finally {
    // What was written becomes the stored base, so the reload below rebases those fields clean
    // while anything typed during the request stays a change.
    if (savedFields.length) {
      stored.value = { ...stored.value, ...Object.fromEntries(savedFields.map((field) => [field, submitted[field]])) }
      productRequest.reload()
    }
    saving.value = false
  }
}

function discard() {
  draft.value = storedDraft(stored.value, Object.keys(stored.value))
}

const leaveUnsaved = () =>
  confirmLeave(__('Discard unsaved changes?'), __('The changes to this product have not been saved.'), __('Discard'))

onBeforeRouteLeave(() => (isDirty.value ? leaveUnsaved() : true))
// Another product opens in this same component, so the leave guard alone never sees it.
onBeforeRouteUpdate((to) => (!isDirty.value || to.params.id === route.params.id ? true : leaveUnsaved()))
useEventListener(window, 'beforeunload', (event) => {
  if (isDirty.value) event.preventDefault()
})

// The server skips a color that is not ready rather than refusing, so a product is publishable once
// one color has none of its blockers (catalog.get_publish_blockers).
const publishBlocker = computed(() => {
  if (!product.value || isLive.value || product.value.status === 'archived') return ''
  const variants = product.value.variants
  if (variants.some((variant) => !variant.blockers?.length)) return ''
  return variants[0]?.blockers?.[0] ?? __('Add a size before you publish.')
})

// publishBlocker reads the first color, so the price link follows that same color.
const isMissingPrice = computed(() => {
  const sizes = publishBlocker.value ? product.value.variants[0].sizes : []
  return sizes.length > 0 && sizes.some((size) => !hasPrice(priceInputs(size).price))
})

// A product sold as one item has its Price on the page; otherwise each color's price is in Variants.
function goToPrice() {
  const section = document.getElementById(singleItem.value ? 'product-pricing' : 'product-variants')
  section?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  section?.querySelector('input')?.focus({ preventScroll: true })
}

async function togglePublish() {
  const publish = !isLive.value
  const toggled = await trySubmit(publishAction, { item_template: product.value.id, publish })
  if (!toggled) return
  const result = publishAction.data
  productRequest.reload()
  if (result.skipped.length) {
    const options = result.skipped.map((skipped) => skipped.option).join(', ')
    const reasons = [...new Set(result.skipped.flatMap((skipped) => skipped.blockers))].join('. ')
    toast.warning(__('Live, except {0}. {1}.', [options, reasons]))
  } else {
    toast.success(publish ? __('Live on your store') : __('Back to draft. Shoppers cannot see it.'))
  }
}

async function toggleArchive() {
  const disabled = product.value.status !== 'archived'
  const saved = await trySubmit(updateAction, { item_template: product.value.id, disabled: disabled ? 1 : 0 })
  if (!saved) return
  toast.success(disabled ? __('Archived') : __('Restored'))
  productRequest.reload()
}

const actions = computed(() =>
  product.value
    ? buildProductActions(product.value, router, {
        onToggleArchive: toggleArchive,
        onReload: () => productRequest.reload(),
      })
    : { groups: [] },
)

const { cards, actionGroup, openAction, record, reload: reloadPlugins } = useRecordPlugins(
  'product',
  'Item',
  () => route.params.id,
  { onReload: () => productRequest.reload() },
)

const hasRail = useMediaQuery('(min-width: 1024px)')

const moreActions = computed(() => [...asDropdownOptions(actions.value.groups), actionGroup.value].filter(Boolean))

const statusLabels = { draft: __('Draft'), live: __('Live'), archived: __('Archived') }
// format.js themes `published` green; Live is that state under its seller-facing name.
const statusKeys = { draft: 'draft', live: 'published', archived: 'archived' }

// A phone has the back button for the way to Products, so the title gets the whole row beside the actions.
const isMobile = useIsMobile()
const breadcrumbs = computed(() => [
  ...(isMobile.value ? [] : [{ label: __('Products'), route: '/products' }]),
  { label: product.value.title },
])

// Below lg the rail is hidden, so the two numbers a seller looks for first ride along at the top.
// A draft with no stock reads calm, as on the products list.
const glance = computed(() => {
  const price = priceRange(stats.value.priceLow, stats.value.priceHigh)
  if (stats.value.onHand <= 0 && !isLive.value) return __('{0} · No stock yet', [price])
  return __('{0} · {1} in stock', [price, stats.value.onHand])
})

watch(
  () => route.params.id,
  () => productRequest.reload(),
)

// A deleted item, a typo in the URL and a permission refusal all settle the same
// way — a finished request holding no product — so the wording is chosen from
// whether the request also kept an error. §2: useAdminRead already toasted that
// error; it is read here to word the page, never to toast it a second time.
const loadFailure = computed(() =>
  productRequest.error
    ? {
        icon: 'lucide-triangle-alert',
        title: __('Could not load this product'),
        description: errorMessage(productRequest.error),
      }
    : {
        icon: 'lucide-search-x',
        title: __('Product not found'),
        description: __('No product matches {0}. It may have been deleted or renamed.', [route.params.id]),
      },
)
</script>

<template>
  <template v-if="product && draft">
    <AppPageHeader :title="product.title" back-to="/products">
      <template #title>
        <Breadcrumbs class="min-w-0" :items="breadcrumbs" />
        <StatusBadge class="ms-1 shrink-0" :status="statusKeys[product.status]" :label="statusLabels[product.status]" />
      </template>
      <template #actions>
        <Dropdown :options="moreActions">
          <Button icon="lucide-ellipsis" :label="__('More actions')" />
        </Dropdown>
        <template v-if="isDirty">
          <span class="hidden text-p-sm text-ink-gray-5 md:inline">
            {{ hasErrors ? __('Fix the highlighted fields to save') : __('Unsaved changes') }}
          </span>
          <Button :label="__('Discard')" variant="subtle" theme="gray" :disabled="saving" @click="discard" />
          <Button
            :label="__('Save')"
            variant="solid"
            theme="gray"
            :loading="saving"
            :disabled="hasErrors"
            @click="save"
          />
        </template>
        <Button
          v-else-if="product.status === 'archived'"
          :label="__('Restore')"
          variant="subtle"
          theme="gray"
          :loading="updateAction.loading"
          @click="toggleArchive"
        />
        <Button
          v-else-if="isLive"
          :label="__('Unpublish')"
          variant="subtle"
          theme="gray"
          :loading="publishAction.loading"
          @click="togglePublish"
        />
        <Button
          v-else
          :label="__('Publish')"
          variant="solid"
          theme="gray"
          :loading="publishAction.loading"
          :disabled="Boolean(publishBlocker)"
          @click="togglePublish"
        />
      </template>
    </AppPageHeader>

    <!-- Two panes, each with its own scroll: the form is long and the summary
         beside it should stay put while you work down the form. -->
    <div class="flex min-h-0 flex-1 overflow-hidden">
      <ScrollArea v-scroll-fade class="min-w-0 flex-1">
        <PageBody width="narrow">
          <div v-if="publishBlocker || !hasRail" class="mb-4 space-y-1">
            <p v-if="publishBlocker" class="flex flex-wrap items-center gap-x-2 text-p-sm text-ink-gray-6">
              {{ publishBlocker }}
              <Button v-if="isMissingPrice" variant="ghost" size="sm" :label="__('Add price')" @click="goToPrice" />
            </p>
            <p v-if="isDirty && hasErrors" class="text-p-sm text-ink-red-6 md:hidden">
              {{ __('Fix the highlighted fields to save') }}
            </p>
            <p v-if="!hasRail" class="text-p-sm text-ink-gray-5 tabular-nums">{{ glance }}</p>
          </div>

          <div class="space-y-6">
            <ProductBasics :draft="draft" :title-error="titleError" />
            <ProductPhotos v-if="product.variants.length" :product="product" @saved="productRequest.reload()" />
            <ProductPricing
              v-if="singleItem"
              :key="singleItem.name"
              :product="product"
              :draft="draft"
              :price-error="priceError"
              :original-price-error="originalPriceMessage"
              @received="productRequest.reload()"
            />
            <VariantEditor :product="product" @saved="productRequest.reload()" />
            <!-- From lg up it sits at the top of the rail, beside the form. -->
            <ProductOrganization class="lg:hidden" :draft="draft" />
            <ProductStorefront :product="product" :is-live="isLive" />
          </div>

          <!-- Below lg the rail is hidden, so the apps' cards stack under the form instead. -->
          <div v-if="cards.length && !hasRail" class="mt-6 space-y-6">
            <PluginSlot :entries="cards" :record="record" frame="stack" @reload="reloadPlugins" />
          </div>
        </PageBody>
      </ScrollArea>

      <aside class="hidden w-72 shrink-0 flex-col border-s border-outline-gray-1 lg:flex">
        <ScrollArea v-scroll-fade class="min-h-0 flex-1">
          <ProductOrganization :draft="draft" layout="rail" />
          <ProductSummaryPanel :product="product" :stats="stats" :is-live="isLive" />
          <PluginSlot v-if="hasRail" :entries="cards" :record="record" frame="rail" @reload="reloadPlugins" />
        </ScrollArea>
      </aside>
    </div>

    <PluginActionDialog v-model:entry="openAction" :record="record" @reload="reloadPlugins" />
  </template>

  <!-- The item code is already in the route, so the header is real from the first
       frame and only the form below waits on the request. The sections are not
       stubbed individually — VariantEditor draws its own placeholders once it has
       a product. -->
  <template v-else-if="productRequest.loading">
    <AppPageHeader
      :title="route.params.id"
      back-to="/products"
      :breadcrumbs="[{ label: __('Products'), route: '/products' }, { label: route.params.id }]"
    />

    <div class="flex min-h-0 flex-1 overflow-hidden">
      <ScrollArea v-scroll-fade class="min-w-0 flex-1">
        <PageBody width="narrow">
          <div class="space-y-6">
            <section v-for="placeholder in 4" :key="placeholder" class="rounded-5 border border-outline-gray-1 p-4">
              <Skeleton class="h-5 w-32 rounded-4" />
              <Skeleton class="mt-1 h-3.5 w-64 rounded-4" />
              <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Skeleton class="h-8 rounded-4" />
                <Skeleton class="h-8 rounded-4" />
              </div>
            </section>
          </div>
        </PageBody>
      </ScrollArea>

      <aside class="hidden w-72 shrink-0 flex-col gap-4 border-s border-outline-gray-1 p-4 lg:flex">
        <Skeleton class="h-4 w-24 rounded-4" />
        <Skeleton class="h-32 w-full rounded-4" />
        <Skeleton class="h-24 w-full rounded-4" />
      </aside>
    </div>
  </template>

  <!-- The request has settled with nothing to show. Without this branch a bad id
       or a refusal falls through every branch above and paints an empty screen. -->
  <template v-else>
    <AppPageHeader
      :title="route.params.id"
      back-to="/products"
      :breadcrumbs="[{ label: __('Products'), route: '/products' }, { label: route.params.id }]"
    />

    <PageBody width="narrow">
      <EmptyState
        :icon="loadFailure.icon"
        :title="loadFailure.title"
        :description="loadFailure.description"
      >
        <Button :label="__('Back to products')" variant="subtle" theme="gray" route="/products" />
      </EmptyState>
    </PageBody>
  </template>
</template>
