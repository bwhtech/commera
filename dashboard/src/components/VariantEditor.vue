<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Dropdown, FormControl, Tooltip, toast } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import DotList from './DotList.vue'
import Thumb from './Thumb.vue'
import EditableValue from './EditableValue.vue'
import FormDialog from './FormDialog.vue'
import VariantDialog from './VariantDialog.vue'
import EditOptionsDialog from './EditOptionsDialog.vue'
import ReceiveStockDialog from './product/ReceiveStockDialog.vue'
import SwatchDot from './SwatchDot.vue'
import { useAdminAction, useAdminRead, trySubmit } from '../data/api'
import { errorMessage } from '../data/errors'
import { money, symbolFor } from '../data/format'
import {
  PLACEHOLDER_ATTRIBUTE,
  hasPrice,
  originalPriceError,
  priceInputRates,
  priceInputs,
  productOptions,
  stockLabel,
} from '../data/product'
import { __ } from '../data/translation'
import { useBulkAction } from '../utils/useBulkAction'
import { useIsMobile } from '../utils/useIsMobile'
import { colorLabel, groupSizes, priceScopeHint, priceUpdatedMessage, stockRows, totalStock } from '../data/variants'

const props = defineProps({ product: { type: Object, required: true } })
const emit = defineEmits(['saved'])

const selection = ref([])

// Held by name: a save reloads the product with new variant objects, and the
// open dialog has to follow them rather than keep showing the old photos.
const editingName = ref(null)
const editing = computed(() => props.product.variants.find((variant) => variant.name === editingName.value) ?? null)
const showVariant = ref(false)
// Set for one opening only: Add price on a phone, where the seller came to type a price.
const focusPrice = ref(false)

function openVariant(variant, { withPriceFocused = false } = {}) {
  editingName.value = variant.name
  focusPrice.value = withPriceFocused
  showVariant.value = true
}

const isUnpriced = (size) => !hasPrice(priceInputs(size).price)

// The inline price editors, by the row they price: a color's name, or a size's item code on a
// product with sizes only, where each size row has its own. A plain object, not a ref: the page
// reads it once per Add price, and a reactive one would re-render the list on every mount.
const priceEditors = {}
function setPriceEditor(key, editor) {
  if (editor) priceEditors[key] = editor
  else delete priceEditors[key]
}

// The page's Add price. On a phone, where the price column is hidden, the first color the publish
// check stops on opens in its dialog. From sm up its inline price editor opens in the row, with the
// caret in the input, so the click visibly lands somewhere and the seller can type at once.
function openFirstUnpriced() {
  const unpriced = props.product.variants.find((variant) => variant.sizes.some(isUnpriced))
  if (!unpriced) return
  if (isMobile.value) {
    openVariant(unpriced, { withPriceFocused: true })
    return
  }
  const key = sizesOnlyVariant.value ? groupSizes(unpriced).find(isUnpriced)?.item_code : unpriced.name
  priceEditors[key]?.open()
}

defineExpose({ openFirstUnpriced })

// "No price", not ₹0, for a row with no price yet: the words the rail, the Products list and the
// publish check use, where a 0 reads as "free".
function priceText(size) {
  const { price } = priceInputs(size)
  return hasPrice(price) ? money(price) : __('No price')
}

const route = useRoute()
const router = useRouter()
watch(
  () => props.product.variants.find((variant) => variant.name === route.query.variant),
  (linked) => {
    if (!linked) return
    openVariant(linked)
    router.replace({ query: { ...route.query, variant: undefined } })
  },
  { immediate: true },
)

const showEditOptions = ref(false)

const options = computed(() => productOptions(props.product))
const hasOptions = computed(() => Boolean(options.value.options.length || options.value.sizes.length))
// Sizes alone keep the hidden "Standard" option, so its one group has no name a seller chose:
// its sizes are listed flat, as the variants they are.
const hasColors = computed(() => Boolean(options.value.options.length))
const sizesOnlyVariant = computed(() => (hasColors.value ? null : props.product.variants[0]))
const optionName = computed(() =>
  props.product.option_attribute && props.product.option_attribute !== PLACEHOLDER_ATTRIBUTE
    ? props.product.option_attribute
    : '',
)

const variantCount = computed(() => props.product.variants.reduce((sum, variant) => sum + variant.sizes.length, 0))
const optionNoun = computed(() => (optionName.value || __('Option')).toLowerCase())
const variantsHint = computed(() => {
  const count = variantCount.value === 1 ? __('1 variant.') : __('{0} variants.', [variantCount.value])
  if (!hasColors.value) return `${count} ${__('Same price for every size.')}`
  // Colors with no sizes: each color is one variant, so its price is its own.
  if (!options.value.sizes.length) return `${count} ${__('Each {0} has its own price.', [optionNoun.value])}`
  return `${count} ${__('Each {0} has one price for all its sizes.', [optionNoun.value])}`
})

// The header counts variants (color × size) and the checkboxes pick colors, so the bulk count names
// what it counts. Only Color has a plural the dashboard can say in a whole translated sentence.
const selectionLabel = computed(() => {
  const count = selection.value.length
  if (optionName.value !== 'Color') return __('{0} selected', [count])
  return count === 1 ? __('1 color selected') : __('{0} colors selected', [count])
})

// Collapsed by default so the colors read as a short list; one group has nothing to collapse into.
const expanded = ref(new Set())
function sizeCount(variant) {
  const count = groupSizes(variant).length
  if (!count) return ''
  return count === 1 ? __('1 size') : __('{0} sizes', [count])
}
// The line under a color's name. A phone has no stock column, so stock joins it there; DotList
// wraps between facts, never inside "0 in stock" or onto a dangling dot, when a Status badge
// narrows the name.
const isMobile = useIsMobile()
function colorFacts(variant) {
  return [sizeCount(variant), isMobile.value && stockLabel(totalStock(variant))].filter(Boolean)
}

const isExpanded = (variant) => props.product.variants.length === 1 || expanded.value.has(variant.name)
function toggleExpanded(variant) {
  const next = new Set(expanded.value)
  if (next.has(variant.name)) next.delete(variant.name)
  else next.add(variant.name)
  expanded.value = next
}

const optionValuesRequest = useAdminRead('catalog.get_attribute_values', {
  params: () => ({ attribute: props.product.option_attribute }),
  immediate: Boolean(optionName.value),
  refetch: true,
})

const swatches = computed(() =>
  Object.fromEntries(
    (optionValuesRequest.data ?? []).map((entry) => [entry.value, { color: entry.color, image: entry.image }]),
  ),
)

// Quiet: a refusal is shown once, under the inline price input, which stays open to retype it.
const priceAction = useAdminAction('catalog.set_variant_price', { quiet: true })

function repricingError(variant, price) {
  if (!hasPrice(price)) return __('Enter a price above zero.')
  return originalPriceError({ ...priceInputs(variant.sizes[0]), price })
}

function repriced(variant, price) {
  return priceInputRates({ ...priceInputs(variant.sizes[0]), price })
}

// EditableValue's `submit`: '' once saved, else the reason, which it shows inline.
async function submitPrice(variant, price) {
  const error = repricingError(variant, price)
  if (error) return error
  try {
    await priceAction.submit({ style_attribute_variant: variant.name, ...repriced(variant, price) })
  } catch (refusal) {
    return errorMessage(refusal)
  }
  toast.success(priceUpdatedMessage(variant))
  emit('saved')
  return ''
}

// Its own quiet request: see Pricing.vue's bulk repricing, which this mirrors.
const bulkPriceAction = useAdminAction('catalog.set_variant_price', { quiet: true })
const { running: bulkRunning, run: runBulk } = useBulkAction()

const currency = symbolFor()
const bulkPriceOpen = ref(false)
const bulkPrice = ref(null)
const bulkPriceTyped = computed(() => bulkPrice.value != null && bulkPrice.value !== '')
const bulkSelected = computed(() => props.product.variants.filter((variant) => selection.value.includes(variant.name)))
const bulkPriceError = computed(() => (hasPrice(bulkPrice.value) ? '' : __('Enter a price above zero.')))
const bulkPriceHint = computed(() => {
  const names = bulkSelected.value.map(colorLabel).join(', ')
  return bulkSelected.value.some((variant) => groupSizes(variant).length)
    ? __('Same price for every size of {0}.', [names])
    : __('For {0}.', [names])
})

function openBulkPrice() {
  bulkPrice.value = null
  bulkPriceOpen.value = true
}

async function bulkSetPrice() {
  if (bulkPriceError.value) return
  const price = Number(bulkPrice.value)
  const names = bulkSelected.value.map(colorLabel).join(', ')
  bulkPriceOpen.value = false
  await runBulk(
    'Set price',
    bulkSelected.value,
    (variant) => {
      const error = repricingError(variant, price)
      if (error) return Promise.reject(new Error(error))
      return bulkPriceAction.submit({ style_attribute_variant: variant.name, ...repriced(variant, price) })
    },
    {
      sentences: {
        all: () => __('Price updated for {0}', [names]),
        some: (done, total, failed) => __('Price updated for {0} of {1}. {2} failed', [done, total, failed]),
      },
      after: ({ failed }) => {
        selection.value = failed.map(({ item }) => item.name)
        emit('saved')
      },
    },
  )
}

const publishAction = useAdminAction('catalog.set_variant_published')

async function togglePublish(variant) {
  const toggled = await trySubmit(publishAction, {
    style_attribute_variant: variant.name,
    publish: variant.is_published ? 0 : 1,
  })
  if (!toggled) return
  toast.success(
    variant.is_published
      ? __('{0} is no longer published', [colorLabel(variant)])
      : __('{0} is live', [colorLabel(variant)]),
  )
  emit('saved')
}

const stockOpen = ref(false)
const stockTarget = ref([])
const allStockRows = computed(() => stockRows(props.product.variants))

function addStock(rows) {
  stockTarget.value = rows
  stockOpen.value = true
}

// Add stock opened from a color's dialog goes back to it, where the held price draft resumes.
const returnToVariant = ref(false)
function addStockFromVariant(rows) {
  returnToVariant.value = true
  addStock(rows)
}
watch(stockOpen, (isOpen) => {
  if (isOpen || !returnToVariant.value) return
  returnToVariant.value = false
  showVariant.value = true
})

function sizeActions(variant, size) {
  return [
    { label: __('Edit price and photos'), icon: 'lucide-pencil', onClick: () => openVariant(variant) },
    { label: __('Add stock'), icon: 'lucide-package-plus', onClick: () => addStock(stockRows([{ ...variant, sizes: [size] }])) },
  ]
}

function rowActions(variant) {
  const label = colorLabel(variant)
  return [
    { label: __('Edit {0}', [label]), icon: 'lucide-pencil', onClick: () => openVariant(variant) },
    { label: __('Add stock'), icon: 'lucide-package-plus', onClick: () => addStock(stockRows([variant])) },
    variant.is_published
      ? { label: __('Unpublish'), icon: 'lucide-eye-off', onClick: () => togglePublish(variant) }
      : {
          label: __('Publish'),
          icon: 'lucide-globe',
          onClick: () => togglePublish(variant),
        },
  ]
}

// A status column earns its place only when the colors differ: the page header's badge already says
// "Not published" or "Live" for the product, and a column repeating it on every row says nothing.
// A blocked color (no price, no photo) differs from a ready one, so it keeps the column too.
function statusKey(variant) {
  if (variant.is_published) return 'live'
  return variant.blockers?.length ? 'blocked' : 'ready'
}
const showsStatus = computed(() => new Set(props.product.variants.map(statusKey)).size > 1)

// Phones get the name, status and menu tracks and read price and stock off the name's second line;
// from sm up those two get their own columns. The cells for them carry max-sm:hidden to match.
const columns = computed(() =>
  showsStatus.value
    ? { base: ['minmax(0,1fr)', 'auto', '2rem'], sm: ['minmax(0,1fr)', '7.5rem', '5.5rem', '7rem', '2rem'] }
    : { base: ['minmax(0,1fr)', '2rem'], sm: ['minmax(0,1fr)', '7.5rem', '5.5rem', '2rem'] },
)

// The color's name sits after the chevron (on a product with sizes and more than one color), the
// button's px-1 and the thumb with gap-3: 28 + 4 + 4 + 32 + 12 = 80px (ps-20), or 48px (ps-12) with
// no chevron. The header label and the size rows use the same inset, so all three start on one
// line. Recheck both numbers if the chevron, the thumb or that gap changes.
const hasChevrons = computed(() => props.product.variants.length > 1 && options.value.sizes.length > 0)
const nameInset = computed(() => (hasChevrons.value ? 'ps-20' : 'ps-12'))

// frappe-ui draws a row divider and the header rule across the grid tracks only, so they start after
// the checkbox column and stop at the row's hover inset. The other product cards rule edge to edge;
// these lift the track placement (inline style, hence !) and stretch both lines over the wrapper's
// px-1 / sm:px-2, so the variant rows rule the same way, sizes included.
const FULL_BLEED_RULES = [
  '[&_[data-slot=list-divider]]:![grid-column:auto]',
  '[&_[data-slot=list-divider]]:-inset-x-1',
  'sm:[&_[data-slot=list-divider]]:-inset-x-2',
  '[&_[data-slot=list-header-border]]:[grid-column:auto]',
  '[&_[data-slot=list-header-border]]:-inset-x-1',
  'sm:[&_[data-slot=list-header-border]]:-inset-x-2',
]
// Sizes alone have no status of their own: the product's status in the page header is theirs.
const sizeColumns = {
  base: ['minmax(0,1fr)', '2rem'],
  sm: ['minmax(0,1fr)', '7.5rem', '5.5rem', '2rem'],
}
</script>

<template>
  <section class="space-y-5">
    <!-- A product that cannot take options (an imported single item) has nothing to show or do
         here: Price and stock already says it sells as one item. -->
    <div v-if="hasOptions || product.can_edit_options" id="product-options" class="rounded-5 border border-outline-gray-1">
      <div class="flex items-start justify-between gap-3 px-4 py-3">
        <div class="min-w-0">
          <h2 class="text-lg-semibold text-ink-gray-8">{{ __('Options') }}</h2>
          <p v-if="!hasOptions" class="mt-1 text-p-sm text-ink-gray-6">
            {{ __('Sell this in more than one size or color.') }}
          </p>
        </div>
        <Button
          v-if="hasOptions"
          :label="__('Edit')"
          icon-left="lucide-pencil"
          @click="showEditOptions = true"
        />
        <Button v-else :label="__('Add options')" icon-left="lucide-plus" @click="showEditOptions = true" />
      </div>

      <dl v-if="hasOptions" class="border-t border-outline-gray-1">
        <div v-if="hasColors" class="flex items-start gap-3 px-4 py-3">
          <dt class="w-20 shrink-0 pt-0.5 text-base text-ink-gray-6">{{ optionName || __('Option') }}</dt>
          <!-- frappe-ui's Badge is nowrap, so a long value held its full width and ran past the card
               at 390px. max-w-full caps each pill at the row (it also caps a flex item's automatic
               minimum), and the inner span truncates; the full value stays in the DOM for a screen
               reader, in the title on hover, and in full as the color's dialog title. -->
          <dd class="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
            <Badge v-for="value in options.options" :key="value" class="max-w-full" variant="subtle" :title="value">
              <span class="flex min-w-0 items-center gap-1.5">
                <SwatchDot
                  v-if="swatches[value]?.color || swatches[value]?.image"
                  :color="swatches[value]?.color"
                  :image="swatches[value]?.image"
                  size="xs"
                />
                <span class="truncate">{{ value }}</span>
              </span>
            </Badge>
          </dd>
        </div>
        <div v-if="options.sizes.length" class="flex items-start gap-3 border-t border-outline-gray-1 px-4 py-3 first:border-t-0">
          <dt class="w-20 shrink-0 pt-0.5 text-base text-ink-gray-6">{{ __('Size') }}</dt>
          <dd class="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
            <Badge v-for="size in options.sizes" :key="size" class="max-w-full" variant="subtle" :title="size">
              <span class="truncate">{{ size }}</span>
            </Badge>
          </dd>
        </div>
      </dl>
    </div>

    <!-- A product with no options shows its one price and stock in the product page's own card. -->
    <div v-if="hasOptions" id="product-variants" class="rounded-5 border border-outline-gray-1">
      <div class="flex flex-wrap items-start justify-between gap-2 px-4 py-3">
        <div class="min-w-0">
          <h2 class="text-lg-semibold text-ink-gray-8">{{ __('Variants') }}</h2>
          <p class="mt-1 text-p-sm text-ink-gray-6 tabular-nums">{{ variantsHint }}</p>
        </div>
        <div class="flex items-center gap-2">
          <template v-if="selection.length">
            <span class="text-sm text-ink-gray-6 tabular-nums">{{ selectionLabel }}</span>
            <Button :label="__('Set price')" :loading="bulkRunning === 'Set price'" @click="openBulkPrice" />
            <Button :label="__('Clear')" variant="ghost" :disabled="Boolean(bulkRunning)" @click="selection = []" />
          </template>
          <Button
            v-else
            :label="__('Add stock')"
            icon-left="lucide-package-plus"
            :disabled="!allStockRows.length"
            @click="addStock(allStockRows)"
          />
        </div>
      </div>

      <!-- Numbers (price, stock) end-align under end-aligned headers, as in the variant dialog's
           sizes table; pe-1.5 matches the px-1.5 of the price trigger and the stock number, so each
           header ends where its values end. -->
      <div class="border-t border-outline-gray-1 px-1 pb-1 sm:px-2">
        <List v-if="sizesOnlyVariant" class="list-row-px-2" :class="FULL_BLEED_RULES" :columns="sizeColumns">
          <ListHeader class="text-ink-gray-6">
            <ListHeaderCell>{{ __('Size') }}</ListHeaderCell>
            <ListHeaderCell class="justify-end pe-1.5 max-sm:hidden">{{ __('Price') }}</ListHeaderCell>
            <ListHeaderCell class="justify-end pe-1.5 max-sm:hidden">{{ __('In stock') }}</ListHeaderCell>
            <ListHeaderCell />
          </ListHeader>

          <ListRows :items="groupSizes(sizesOnlyVariant)" row-key="item_code" v-slot="{ item: size }">
            <ListRow class="min-h-11 py-1">
              <ListCell class="min-w-0">
                <button
                  type="button"
                  class="-ms-1 min-w-0 rounded-4 px-1 py-0.5 text-start hover:bg-surface-gray-2"
                  @click.stop="openVariant(sizesOnlyVariant)"
                >
                  <span class="block truncate text-base-medium text-ink-gray-8">{{ size.size }}</span>
                  <span class="block text-sm text-ink-gray-6 tabular-nums sm:hidden">
                    {{ priceText(size) }}
                    <span v-if="priceInputs(size).originalPrice" class="line-through">{{ money(priceInputs(size).originalPrice) }}</span>
                    · {{ stockLabel(size.stock) }}
                  </span>
                </button>
              </ListCell>
              <ListCell class="flex-col !items-end max-sm:hidden" data-price-cell>
                <EditableValue
                  :ref="(editor) => setPriceEditor(size.item_code, editor)"
                  :model-value="priceInputs(size).price"
                  :empty-label="__('No price')"
                  :label="__('Price')"
                  :description="priceScopeHint(sizesOnlyVariant)"
                  :trigger-label="__('Edit price of {0}', [product.title])"
                  :submit="(price) => submitPrice(sizesOnlyVariant, price)"
                  format="money"
                  align="end"
                />
                <span v-if="priceInputs(size).originalPrice" class="pe-1.5 text-sm text-ink-gray-6 line-through tabular-nums">
                  {{ money(priceInputs(size).originalPrice) }}
                </span>
              </ListCell>
              <ListCell class="justify-end max-sm:hidden">
                <span class="px-1.5 text-base tabular-nums" :class="size.stock ? 'text-ink-gray-8' : 'text-ink-gray-6'">
                  {{ size.stock ?? 0 }}
                </span>
              </ListCell>
              <ListCell class="justify-end">
                <Dropdown :options="sizeActions(sizesOnlyVariant, size)" @click.stop>
                  <Button icon="lucide-ellipsis" variant="ghost" :label="__('More actions for {0}', [size.size])" />
                </Dropdown>
              </ListCell>
            </ListRow>
          </ListRows>
        </List>

        <List v-else v-model:selection="selection" class="list-row-px-2" :class="FULL_BLEED_RULES" selectable :columns="columns">
          <ListHeader class="text-ink-gray-6">
            <ListHeaderCell :class="nameInset">{{ optionName || __('Option') }}</ListHeaderCell>
            <ListHeaderCell class="justify-end pe-1.5 max-sm:hidden">{{ __('Price') }}</ListHeaderCell>
            <ListHeaderCell class="justify-end pe-1.5 max-sm:hidden">{{ __('In stock') }}</ListHeaderCell>
            <ListHeaderCell v-if="showsStatus">{{ __('Status') }}</ListHeaderCell>
            <ListHeaderCell />
          </ListHeader>

          <ListRows :items="product.variants" row-key="name" v-slot="{ item }">
            <ListRow :value="item.name" class="min-h-12 py-1.5">
              <ListCell class="min-w-0">
                <div class="flex min-w-0 items-center gap-1">
                  <template v-if="hasChevrons">
                    <Button
                      v-if="groupSizes(item).length"
                      variant="ghost"
                      size="sm"
                      :icon="isExpanded(item) ? 'lucide-chevron-down' : 'lucide-chevron-right rtl:-scale-x-100'"
                      :label="isExpanded(item) ? __('Hide sizes of {0}', [colorLabel(item)]) : __('Show sizes of {0}', [colorLabel(item)])"
                      @click.stop="toggleExpanded(item)"
                    />
                    <!-- A color whose sizes were all taken out keeps the chevron's width, so its name
                         stays on the line nameInset draws. -->
                    <span v-else class="size-7 shrink-0" aria-hidden="true" />
                  </template>
                  <button
                    type="button"
                    class="flex min-w-0 items-center gap-3 rounded-4 px-1 py-0.5 text-start hover:bg-surface-gray-2"
                    @click.stop="openVariant(item)"
                  >
                    <Thumb :image="item.images[0]" size="size-8" />
                    <span class="min-w-0">
                      <span class="block truncate text-base-medium text-ink-gray-8">{{ colorLabel(item) }}</span>
                      <!-- On a phone the price gets a line of its own. Neither line truncates: they
                           are the only place a phone shows these numbers. -->
                      <DotList class="text-sm text-ink-gray-6 tabular-nums" :parts="colorFacts(item)" />
                      <span class="block text-sm text-ink-gray-6 tabular-nums sm:hidden">
                        {{ priceText(item.sizes[0]) }}
                        <span v-if="priceInputs(item.sizes[0]).originalPrice" class="line-through">{{ money(priceInputs(item.sizes[0]).originalPrice) }}</span>
                      </span>
                    </span>
                  </button>
                </div>
              </ListCell>
              <!-- One price for the whole color: set_variant_price writes every size under it. The
                   original price sits under it, as the sizes line sits under the name, so the charged
                   prices keep one right edge down the column whether a row has one or not. -->
              <ListCell class="flex-col !items-end max-sm:hidden" data-price-cell>
                <EditableValue
                  :ref="(editor) => setPriceEditor(item.name, editor)"
                  :model-value="priceInputs(item.sizes[0]).price"
                  :empty-label="__('No price')"
                  :label="__('Price')"
                  :description="priceScopeHint(item) || undefined"
                  :trigger-label="__('Edit price of {0}', [colorLabel(item)])"
                  :submit="(price) => submitPrice(item, price)"
                  format="money"
                  align="end"
                />
                <span v-if="priceInputs(item.sizes[0]).originalPrice" class="pe-1.5 text-sm text-ink-gray-6 line-through tabular-nums">
                  {{ money(priceInputs(item.sizes[0]).originalPrice) }}
                </span>
              </ListCell>
              <ListCell class="justify-end max-sm:hidden">
                <span class="px-1.5 text-base tabular-nums" :class="totalStock(item) ? 'text-ink-gray-8' : 'text-ink-gray-6'">
                  {{ totalStock(item) }}
                </span>
              </ListCell>
              <ListCell v-if="showsStatus">
                <Badge v-if="item.is_published" :label="__('Live')" theme="green" variant="subtle" />
                <Tooltip v-else-if="item.blockers?.length" :text="item.blockers.join(', ')">
                  <Badge :label="__('Not published')" theme="gray" variant="subtle">
                    <template #suffix><span class="lucide-info size-3" aria-hidden="true" /></template>
                  </Badge>
                </Tooltip>
                <Badge v-else :label="__('Not published')" theme="gray" variant="subtle" />
              </ListCell>
              <ListCell class="justify-end">
                <Dropdown :options="rowActions(item)" @click.stop>
                  <Button icon="lucide-ellipsis" variant="ghost" :label="__('More actions for {0}', [colorLabel(item)])" />
                </Dropdown>
              </ListCell>
            </ListRow>

            <!-- Sizes as plain rows under their color: no value, so no checkbox, and they keep
                 the list's row-after-row dividers. Stock is added from the color's menu. -->
            <template v-if="isExpanded(item)">
              <ListRow v-for="size in groupSizes(item)" :key="size.item_code" class="min-h-11 py-1">
                <ListCell class="min-w-0" :class="nameInset">
                  <span class="min-w-0">
                    <span class="block truncate text-base text-ink-gray-8">{{ size.size }}</span>
                    <span class="block text-sm text-ink-gray-6 tabular-nums sm:hidden">{{ stockLabel(size.stock) }}</span>
                  </span>
                </ListCell>
                <ListCell class="max-sm:hidden" />
                <ListCell class="justify-end max-sm:hidden">
                  <span class="px-1.5 text-base tabular-nums" :class="size.stock ? 'text-ink-gray-8' : 'text-ink-gray-6'">
                    {{ size.stock ?? 0 }}
                  </span>
                </ListCell>
                <ListCell :class="{ 'col-span-2': showsStatus }" />
              </ListRow>
            </template>
          </ListRows>
        </List>
      </div>
    </div>
  </section>

  <EditOptionsDialog v-model:open="showEditOptions" :product="product" @saved="emit('saved')" />
  <VariantDialog
    v-model:open="showVariant"
    :variant="editing"
    :product="product"
    :focus-price="focusPrice"
    @saved="emit('saved')"
    @add-stock="addStockFromVariant"
  />
  <ReceiveStockDialog v-model:open="stockOpen" :rows="stockTarget" @received="emit('saved')" />
  <FormDialog
    v-model:open="bulkPriceOpen"
    size="md"
    :title="__('Set price')"
    :primary-label="__('Set price')"
    :primary-disabled="Boolean(bulkPriceError)"
    :reason="bulkPriceError"
    :dirty="bulkPriceTyped"
    @submit="bulkSetPrice"
  >
    <FormControl
      v-model.number="bulkPrice"
      type="number"
      inputmode="decimal"
      placeholder="0"
      :label="__('Price')"
      required
      :description="bulkPriceHint"
    >
      <template #prefix><span class="text-base text-ink-gray-6">{{ currency }}</span></template>
    </FormControl>
  </FormDialog>
</template>
