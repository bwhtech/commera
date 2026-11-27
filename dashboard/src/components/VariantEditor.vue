<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Dropdown, FormControl, Tooltip, toast } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import Thumb from './Thumb.vue'
import EditableValue from './EditableValue.vue'
import FormDialog from './FormDialog.vue'
import VariantDialog from './VariantDialog.vue'
import EditOptionsDialog from './EditOptionsDialog.vue'
import ReceiveStockDialog from './product/ReceiveStockDialog.vue'
import SwatchDot from './SwatchDot.vue'
import { useAdminAction, useAdminRead, trySubmit } from '../data/api'
import { money, symbolFor } from '../data/format'
import {
  PLACEHOLDER_ATTRIBUTE,
  hasPrice,
  originalPriceError,
  priceInputRates,
  priceInputs,
  productOptions,
} from '../data/product'
import { __ } from '../data/translation'
import { useBulkAction } from '../utils/useBulkAction'
import { colorLabel, groupSizes, priceScopeHint, priceUpdatedMessage, stockRows, totalStock } from '../data/variants'

const props = defineProps({ product: { type: Object, required: true } })
const emit = defineEmits(['saved'])

const selection = ref([])

// Held by name: a save reloads the product with new variant objects, and the
// open dialog has to follow them rather than keep showing the old photos.
const editingName = ref(null)
const editing = computed(() => props.product.variants.find((variant) => variant.name === editingName.value) ?? null)
const showVariant = ref(false)

function openVariant(variant) {
  editingName.value = variant.name
  showVariant.value = true
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
const variantsHint = computed(() => {
  const count = variantCount.value === 1 ? __('1 variant.') : __('{0} variants.', [variantCount.value])
  if (!hasColors.value) return `${count} ${__('Same price for every size.')}`
  return `${count} ${__('Each {0} has one price for all its sizes.', [optionName.value.toLowerCase()])}`
})

// Collapsed by default so the colors read as a short list; one group has nothing to collapse into.
const expanded = ref(new Set())
function sizeCount(variant) {
  const count = groupSizes(variant).length
  if (!count) return ''
  return count === 1 ? __('1 size') : __('{0} sizes', [count])
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

const priceAction = useAdminAction('catalog.set_variant_price')

function repricingError(variant, price) {
  if (!hasPrice(price)) return __('Enter a price above zero.')
  return originalPriceError({ ...priceInputs(variant.sizes[0]), price })
}

function repriced(variant, price) {
  return priceInputRates({ ...priceInputs(variant.sizes[0]), price })
}

async function setPrice(variant, price) {
  const error = repricingError(variant, price)
  if (error) return toast.error(error)
  const saved = await trySubmit(priceAction, { style_attribute_variant: variant.name, ...repriced(variant, price) })
  if (!saved) return
  toast.success(priceUpdatedMessage(variant))
  emit('saved')
}

// Its own quiet request: see Pricing.vue's bulk repricing, which this mirrors.
const bulkPriceAction = useAdminAction('catalog.set_variant_price', { quiet: true })
const { running: bulkRunning, run: runBulk } = useBulkAction()

const currency = symbolFor()
const bulkPriceOpen = ref(false)
const bulkPrice = ref(null)
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
      ? __('{0} is now a draft', [colorLabel(variant)])
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

// Phones get three tracks (name, status, menu) and read price and stock off the name's second
// line; from sm up those two get their own columns. The cells for them carry max-sm:hidden to match.
const columns = {
  base: ['minmax(0,1fr)', '3.5rem', '2rem'],
  sm: ['minmax(0,1fr)', '7.5rem', '5.5rem', '5.5rem', '2rem'],
}
// Sizes alone have no status of their own: the product's status in the page header is theirs.
const sizeColumns = {
  base: ['minmax(0,1fr)', '2rem'],
  sm: ['minmax(0,1fr)', '7.5rem', '5.5rem', '2rem'],
}
</script>

<template>
  <section class="space-y-5">
    <div id="product-options" class="rounded-5 border border-outline-gray-1">
      <div class="flex items-start justify-between gap-3 px-4 py-3">
        <div class="min-w-0">
          <h2 class="text-lg-semibold text-ink-gray-8">{{ __('Options') }}</h2>
          <p v-if="!hasOptions" class="mt-1 text-p-sm text-ink-gray-5">
            {{ product.can_edit_options ? __('Sell this in more than one size or color.') : __('It sells as a single item.') }}
          </p>
        </div>
        <Button
          v-if="hasOptions && product.can_edit_options"
          :label="__('Edit')"
          icon-left="lucide-pencil"
          @click="showEditOptions = true"
        />
      </div>

      <dl v-if="hasOptions" class="border-t border-outline-gray-1">
        <div v-if="hasColors" class="flex items-start gap-3 px-4 py-3">
          <dt class="w-20 shrink-0 pt-0.5 text-base text-ink-gray-6">{{ optionName || __('Option') }}</dt>
          <dd class="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
            <Badge v-for="value in options.options" :key="value" variant="subtle">
              <span class="flex items-center gap-1.5">
                <SwatchDot
                  v-if="swatches[value]?.color || swatches[value]?.image"
                  :color="swatches[value]?.color"
                  :image="swatches[value]?.image"
                  size="xs"
                />
                {{ value }}
              </span>
            </Badge>
          </dd>
        </div>
        <div v-if="options.sizes.length" class="flex items-start gap-3 border-t border-outline-gray-1 px-4 py-3 first:border-t-0">
          <dt class="w-20 shrink-0 pt-0.5 text-base text-ink-gray-6">{{ __('Size') }}</dt>
          <dd class="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
            <Badge v-for="size in options.sizes" :key="size" :label="size" variant="subtle" />
          </dd>
        </div>
      </dl>

      <div v-else-if="product.can_edit_options" class="border-t border-outline-gray-1 px-2 py-2">
        <Button
          variant="ghost"
          icon-left="lucide-plus"
          :label="__('Add options like size or color')"
          @click="showEditOptions = true"
        />
      </div>
    </div>

    <!-- A product with no options shows its one price and stock in the product page's own card. -->
    <div v-if="hasOptions" id="product-variants" class="rounded-5 border border-outline-gray-1">
      <div class="flex flex-wrap items-start justify-between gap-2 px-4 py-3">
        <div class="min-w-0">
          <h2 class="text-lg-semibold text-ink-gray-8">{{ __('Variants') }}</h2>
          <p class="mt-1 text-p-sm text-ink-gray-5">{{ variantsHint }}</p>
        </div>
        <div class="flex items-center gap-2">
          <template v-if="selection.length">
            <span class="text-sm text-ink-gray-5">{{ __('{0} selected', [selection.length]) }}</span>
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

      <div class="border-t border-outline-gray-1 px-1 pb-1 sm:px-2">
        <List v-if="sizesOnlyVariant" class="list-row-px-2" :columns="sizeColumns">
          <ListHeader>
            <ListHeaderCell>{{ __('Size') }}</ListHeaderCell>
            <ListHeaderCell class="max-sm:hidden">{{ __('Price') }}</ListHeaderCell>
            <ListHeaderCell class="max-sm:hidden">{{ __('In stock') }}</ListHeaderCell>
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
                  <span class="block truncate text-sm text-ink-gray-5 sm:hidden">
                    {{ money(priceInputs(size).price ?? 0) }}
                    <span v-if="priceInputs(size).originalPrice" class="line-through">{{ money(priceInputs(size).originalPrice) }}</span>
                    · {{ __('{0} in stock', [size.stock ?? 0]) }}
                  </span>
                </button>
              </ListCell>
              <ListCell class="max-sm:hidden">
                <EditableValue
                  :model-value="priceInputs(size).price ?? 0"
                  :label="__('Price')"
                  :description="priceScopeHint(sizesOnlyVariant)"
                  format="money"
                  @update:model-value="(price) => setPrice(sizesOnlyVariant, price)"
                />
                <span v-if="priceInputs(size).originalPrice" class="text-sm text-ink-gray-4 line-through tabular-nums">
                  {{ money(priceInputs(size).originalPrice) }}
                </span>
              </ListCell>
              <ListCell class="max-sm:hidden">
                <span class="px-1.5 text-base tabular-nums" :class="size.stock ? 'text-ink-gray-8' : 'text-ink-gray-5'">
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

        <List v-else v-model:selection="selection" class="list-row-px-2" selectable :columns="columns">
          <ListHeader>
            <ListHeaderCell>{{ optionName || __('Option') }}</ListHeaderCell>
            <ListHeaderCell class="max-sm:hidden">{{ __('Price') }}</ListHeaderCell>
            <ListHeaderCell class="max-sm:hidden">{{ __('In stock') }}</ListHeaderCell>
            <ListHeaderCell>{{ __('Status') }}</ListHeaderCell>
            <ListHeaderCell />
          </ListHeader>

          <ListRows :items="product.variants" row-key="name" v-slot="{ item }">
            <ListRow :value="item.name" class="min-h-12 py-1.5">
              <ListCell class="min-w-0">
                <div class="flex min-w-0 items-center gap-1">
                  <Button
                    v-if="groupSizes(item).length && product.variants.length > 1"
                    variant="ghost"
                    size="sm"
                    :icon="isExpanded(item) ? 'lucide-chevron-down' : 'lucide-chevron-right rtl:-scale-x-100'"
                    :label="isExpanded(item) ? __('Hide sizes of {0}', [colorLabel(item)]) : __('Show sizes of {0}', [colorLabel(item)])"
                    @click.stop="toggleExpanded(item)"
                  />
                  <button
                    type="button"
                    class="flex min-w-0 items-center gap-2.5 rounded-4 px-1 py-0.5 text-start hover:bg-surface-gray-2"
                    @click.stop="openVariant(item)"
                  >
                    <Thumb :image="item.images[0]" size="size-8" />
                    <span class="min-w-0">
                      <span class="block truncate text-base-medium text-ink-gray-8">{{ colorLabel(item) }}</span>
                      <!-- On a phone, stock joins the sizes line and the price gets a line of its own. -->
                      <span class="block truncate text-sm text-ink-gray-5">
                        {{ sizeCount(item) }}<span class="sm:hidden">{{ sizeCount(item) ? ' · ' : '' }}{{ __('{0} in stock', [totalStock(item)]) }}</span>
                      </span>
                      <span class="block truncate text-sm text-ink-gray-5 sm:hidden">
                        {{ money(priceInputs(item.sizes[0]).price ?? 0) }}
                        <span v-if="priceInputs(item.sizes[0]).originalPrice" class="line-through">{{ money(priceInputs(item.sizes[0]).originalPrice) }}</span>
                      </span>
                    </span>
                  </button>
                </div>
              </ListCell>
              <ListCell class="max-sm:hidden">
                <!-- One price for the whole color: set_variant_price writes every size under it. -->
                <EditableValue
                  :model-value="priceInputs(item.sizes[0]).price ?? 0"
                  :label="__('Price')"
                  :description="priceScopeHint(item) || undefined"
                  format="money"
                  @update:model-value="(price) => setPrice(item, price)"
                />
                <span v-if="priceInputs(item.sizes[0]).originalPrice" class="text-sm text-ink-gray-4 line-through tabular-nums">
                  {{ money(priceInputs(item.sizes[0]).originalPrice) }}
                </span>
              </ListCell>
              <ListCell class="max-sm:hidden">
                <span class="px-1.5 text-base tabular-nums" :class="totalStock(item) ? 'text-ink-gray-8' : 'text-ink-gray-5'">
                  {{ totalStock(item) }}
                </span>
              </ListCell>
              <ListCell>
                <Badge v-if="item.is_published" :label="__('Live')" theme="green" variant="subtle" />
                <Tooltip v-else-if="item.blockers?.length" :text="item.blockers.join(', ')">
                  <Badge :label="__('Draft')" theme="gray" variant="subtle">
                    <template #suffix><span class="lucide-info size-3" aria-hidden="true" /></template>
                  </Badge>
                </Tooltip>
                <Badge v-else :label="__('Draft')" theme="gray" variant="subtle" />
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
                <!-- Indented to the color's name, which sits after the chevron (when there is one) and the thumb. -->
                <ListCell class="min-w-0" :class="product.variants.length > 1 ? 'ps-20' : 'ps-12'">
                  <span class="min-w-0">
                    <span class="block truncate text-base text-ink-gray-8">{{ size.size }}</span>
                    <span class="block truncate text-sm text-ink-gray-5 sm:hidden">{{ __('{0} in stock', [size.stock ?? 0]) }}</span>
                  </span>
                </ListCell>
                <ListCell class="max-sm:hidden" />
                <ListCell class="max-sm:hidden">
                  <span class="px-1.5 text-base tabular-nums" :class="size.stock ? 'text-ink-gray-8' : 'text-ink-gray-5'">
                    {{ size.stock ?? 0 }}
                  </span>
                </ListCell>
                <ListCell class="col-span-2" />
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
    @submit="bulkSetPrice"
  >
    <FormControl
      v-model.number="bulkPrice"
      type="number"
      :label="__('Price')"
      required
      :description="bulkPriceHint"
    >
      <template #prefix><span class="text-base text-ink-gray-5">{{ currency }}</span></template>
    </FormControl>
  </FormDialog>
</template>
