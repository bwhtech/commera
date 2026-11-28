<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { useEventListener, useMediaQuery } from '@vueuse/core'
import { Alert, Breadcrumbs, Button, Dropdown, ScrollArea, Skeleton, toast } from 'frappe-ui'
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
import {
  hasPrice,
  originalPriceError,
  priceInputRates,
  priceInputs,
  productOptions,
  useProductStats,
} from '../data/product'
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
    size_order: data.size_order,
    option_attribute: data.option_attribute,
    can_edit_options: data.can_edit_options,
    recent_sales: data.recent_sales,
  }
})

// A second reload while one is in flight aborts the first mid-body, and frappe-ui's fetch logs that
// abort as a "programming error". Writes here land in quick runs (a photo removed, then its undo; a
// stock receipt, then a cover change), so a reload asked for during one runs once after it instead.
let reloadQueued = false
function reloadProduct() {
  if (productRequest.loading) {
    reloadQueued = true
    return
  }
  productRequest.reload()
}
watch(
  () => productRequest.loading,
  (loading) => {
    if (loading || !reloadQueued) return
    reloadQueued = false
    productRequest.reload()
  },
)

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
      reloadProduct()
    }
    saving.value = false
    // A refused Save keeps Save on screen, but its spinner disabled it and the browser dropped focus
    // to the page; a keyboard user gets it back, as after a refused Publish.
    if (isDirty.value) refocus(saveButton)
  }
  // Reached only when every write took (a refusal returns above); with nothing typed meanwhile,
  // Save and Discard are gone from the header.
  if (!isDirty.value) {
    draftVersion.value += 1
    focusMoreActions()
  }
}

// Save and Discard leave the header as they finish (the header swaps them for the status button),
// so the button that had focus unmounts and focus would fall to the page. It goes to More actions:
// not to Publish, where a second Enter would publish with no confirmation.
const moreActionsButton = ref(null)
// A reset or saved draft starts its form afresh: see ProductPricing's PriceFields key.
const draftVersion = ref(0)

async function focusMoreActions() {
  await nextTick()
  if (document.activeElement && document.activeElement !== document.body) return
  moreActionsButton.value?.$el?.focus({ preventScroll: true })
}

function discard() {
  draft.value = storedDraft(stored.value, Object.keys(stored.value))
  draftVersion.value += 1
  focusMoreActions()
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

const variantEditor = ref(null)

// A product sold as one item has its Price on the page, so Price takes focus. Otherwise each color
// has its own price, and VariantEditor opens the first one the publish check stops on: in its
// dialog on a phone, which hides the price column, and in its row's inline editor from sm up.
// Focusing a closed price trigger instead left a pointer click with no ring and nothing open.
function goToPrice() {
  if (!singleItem.value) {
    if (!isMobile.value) document.getElementById('product-variants')?.scrollIntoView({ block: 'start' })
    variantEditor.value?.openFirstUnpriced()
    return
  }
  const section = document.getElementById('product-pricing')
  section?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  section?.querySelector('input')?.focus({ preventScroll: true })
}

// Gray subtle, not the Alert's default amber label: amber ink on the Alert's gray-1 surface measures
// 3.0:1 in light mode. Naming a variant and theme is what makes frappe-ui skip that override.
const addPriceAction = computed(() =>
  isMissingPrice.value ? { label: __('Add price'), variant: 'subtle', theme: 'gray', onClick: goToPrice } : undefined,
)

// The status button shows a spinner while its request runs, and the browser drops focus from a
// disabled button to the page. Once it settles, a keyboard user is handed back to the same button
// (now Unpublish, Publish or Restore); a click elsewhere meanwhile keeps its own focus.
const statusButton = ref(null)

const saveButton = ref(null)

async function refocus(button) {
  await nextTick()
  if (document.activeElement && document.activeElement !== document.body) return
  button.value?.$el?.focus({ preventScroll: true })
}

const refocusStatusButton = () => refocus(statusButton)

async function togglePublish() {
  const publish = !isLive.value
  const toggled = await trySubmit(publishAction, { item_template: product.value.id, publish })
  refocusStatusButton()
  if (!toggled) return
  const result = publishAction.data
  reloadProduct()
  if (result.skipped.length) {
    const options = result.skipped.map((skipped) => skipped.option).join(', ')
    const reasons = [...new Set(result.skipped.flatMap((skipped) => skipped.blockers))].join('. ')
    toast.warning(__('Live, except {0}. {1}.', [options, reasons]))
  } else {
    toast.success(publish ? __('Live on your store') : __('Not published. Shoppers cannot see it.'))
  }
}

async function toggleArchive() {
  const disabled = product.value.status !== 'archived'
  const saved = await trySubmit(updateAction, { item_template: product.value.id, disabled: disabled ? 1 : 0 })
  refocusStatusButton()
  if (!saved) return
  toast.success(disabled ? __('Archived') : __('Restored'))
  reloadProduct()
}

// Restore, Unpublish and Publish are one button whose label and action follow the status, so the
// element that was pressed is the one that stays: three v-if buttons swapped on every toggle, and
// the pressed one unmounted with keyboard focus inside it.
const statusAction = computed(() => {
  if (product.value?.status === 'archived') {
    return { label: __('Restore'), variant: 'subtle', loading: updateAction.loading, disabled: false, onClick: toggleArchive }
  }
  if (isLive.value) {
    return { label: __('Unpublish'), variant: 'subtle', loading: publishAction.loading, disabled: false, onClick: togglePublish }
  }
  return {
    label: __('Publish'),
    variant: 'solid',
    loading: publishAction.loading,
    disabled: Boolean(publishBlocker.value),
    onClick: togglePublish,
  }
})

const actions = computed(() =>
  product.value
    ? buildProductActions(product.value, router, {
        onToggleArchive: toggleArchive,
        onReload: reloadProduct,
        // A menu item unmounts with its menu, so a dialog it opened returns focus to the menu's button.
        returnFocus: () => moreActionsButton.value?.$el?.focus({ preventScroll: true }),
      })
    : { groups: [] },
)

const { cards, actionGroup, openAction, record, reload: reloadPlugins } = useRecordPlugins(
  'product',
  'Item',
  () => route.params.id,
  { onReload: reloadProduct },
)

const hasRail = useMediaQuery('(min-width: 1024px)')

const moreActions = computed(() => [...asDropdownOptions(actions.value.groups), actionGroup.value].filter(Boolean))

const statusLabels = { draft: __('Not published'), live: __('Live'), archived: __('Archived') }
// format.js themes `published` green; Live is that state under its seller-facing name.
const statusKeys = { draft: 'draft', live: 'published', archived: 'archived' }

// A phone has the back button for the way to Products, so the title gets the whole row beside the actions.
const isMobile = useIsMobile()
const breadcrumbs = computed(() => [
  ...(isMobile.value ? [] : [{ label: __('Products'), route: '/products' }]),
  { label: product.value.title },
])

// Below lg the rail is hidden, so the two numbers a seller looks for first ride along at the top,
// except on a product sold as one item, whose Price and stock card already shows them.
const showsGlance = computed(() => !hasRail.value && !singleItem.value)
// Zero reads "0 in stock", as on the variant rows and in stockLabel().
const glance = computed(() =>
  __('{0} · {1} in stock', [priceRange(stats.value.priceLow, stats.value.priceHigh), stats.value.onHand]),
)

// Another product opening in this component needs no reload of its own: `refetch` re-runs the read
// when its params change, and a second request here would abort that one.

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
        <!-- align="end": start-aligned, the menu overran the window and frappe-ui's collision
             handling pushed it flush against the screen edge. -->
        <Dropdown :options="moreActions" align="end">
          <Button ref="moreActionsButton" icon="lucide-ellipsis" :label="__('More actions')" />
        </Dropdown>
        <template v-if="isDirty">
          <!-- The error in the red of the field errors below it, as on a phone; plain unsaved work
               stays a gray status. -->
          <span class="hidden text-p-sm md:inline" :class="hasErrors ? 'text-ink-red-7' : 'text-ink-gray-6'">
            {{ hasErrors ? __('Fix the highlighted fields to save.') : __('Unsaved changes') }}
          </span>
          <Button :label="__('Discard')" variant="subtle" theme="gray" :disabled="saving" @click="discard" />
          <Button
            ref="saveButton"
            :label="__('Save')"
            variant="solid"
            theme="gray"
            :loading="saving"
            :disabled="hasErrors"
            @click="save"
          />
        </template>
        <Button
          v-else
          ref="statusButton"
          :label="statusAction.label"
          :variant="statusAction.variant"
          theme="gray"
          :loading="statusAction.loading"
          :disabled="statusAction.disabled"
          @click="statusAction.onClick"
        />
      </template>
    </AppPageHeader>

    <!-- Two panes, each with its own scroll: the form is long and the summary
         beside it should stay put while you work down the form. -->
    <div class="flex min-h-0 flex-1 overflow-hidden">
      <ScrollArea v-scroll-fade class="min-w-0 flex-1">
        <PageBody width="narrow">
          <div v-if="publishBlocker || showsGlance || (!hasRail && isDirty && hasErrors)" class="mb-4 space-y-1">
            <Alert v-if="publishBlocker" theme="amber" :title="publishBlocker" :primary-action="addPriceAction" />
            <!-- red-7, the field errors' red (style.css), so this line and "Enter a title." under it
                 read as one red: red-6 measured 4.84:1 on the dark page. -->
            <p v-if="isDirty && hasErrors" class="text-p-sm text-ink-red-7 md:hidden">
              {{ __('Fix the highlighted fields to save.') }}
            </p>
            <p v-if="showsGlance" class="text-p-sm text-ink-gray-6 tabular-nums">{{ glance }}</p>
          </div>

          <div class="space-y-6">
            <ProductBasics :draft="draft" :title-error="titleError" />
            <ProductPhotos v-if="product.variants.length" :product="product" @saved="reloadProduct" />
            <ProductPricing
              v-if="singleItem"
              :key="singleItem.name"
              :product="product"
              :draft="draft"
              :draft-version="draftVersion"
              :price-error="priceError"
              :original-price-error="originalPriceMessage"
              @received="reloadProduct"
            />
            <VariantEditor ref="variantEditor" :product="product" @saved="reloadProduct" />
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
          <ProductSummaryPanel :product="product" :stats="stats" :is-live="isLive" :is-single-item="Boolean(singleItem)" />
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
