<script setup>
/**
 * Create a sellable product in one screen: catalog.create_product does the rest
 * (Item template + variants, Style Attribute Configurator, generate_variants, prices).
 * Company, warehouse, price list, UOM and naming series are resolved server-side —
 * this dialog never shows an ERPNext concept the owner did not ask for.
 */
import { computed, ref, watch } from 'vue'
import { Button, ErrorMessage, FormControl, Select, dialog, toast } from 'frappe-ui'
import { useRouter } from 'vue-router'
import { useAdminAction, useAdminRead, trySubmit } from '../data/api'
import { addProduct, closeAddProduct } from '../data/addProduct'
import { newProductOptionSizes } from '../data/optionSizes'
import { hasPrice, originalPriceError, priceInputRates } from '../data/product'
import { productRoute } from '../ia/routes'
import { __ } from '../data/translation'
import AttributeMultiSelect from './AttributeMultiSelect.vue'
import FormDialog from './FormDialog.vue'
import OptionSizeGrid from './OptionSizeGrid.vue'
import PriceFields from './PriceFields.vue'

const router = useRouter()

const title = ref('')
const titleError = ref('')
const price = ref(null)
const originalPrice = ref(null)
const collection = ref('')
const showOptions = ref(false)
const showOtherOptions = ref(false)
const optionAttribute = ref('Color')
const colors = ref([])
const sizes = ref([])
const excludedPairs = ref([])
const colorsOpen = ref(false)
const sizesOpen = ref(false)
const optionSwatches = ref({})

function setOptionSwatches(values) {
  optionSwatches.value = Object.fromEntries(
    values.map((entry) => [entry.value, { color: entry.color, image: entry.image }]),
  )
}

// reka guards only Escape by topmost layer, so one outside click dismisses the
// popover and the dialog both; the dialog yields while a picker owns that click.
const pickerOpen = computed(() => colorsOpen.value || sizesOpen.value)

const collectionsRequest = useAdminRead('catalog.get_collections')
const defaultCollectionRequest = useAdminRead('catalog.get_default_collection')
const collectionOptions = computed(() =>
  (collectionsRequest.data ?? []).map((name) => ({ label: name, value: name })),
)

function clearOptions() {
  showOptions.value = false
  showOtherOptions.value = false
  optionAttribute.value = 'Color'
  colors.value = []
  sizes.value = []
  excludedPairs.value = []
}

async function resetForm() {
  title.value = ''
  titleError.value = ''
  price.value = null
  originalPrice.value = null
  clearOptions()
  collection.value = ''
  collectionsRequest.reload()
  // Preselected where the last product went; an owner who picks another before this answers keeps it.
  await defaultCollectionRequest.reload()
  if (!collection.value) collection.value = defaultCollectionRequest.data ?? ''
}

watch(
  () => addProduct.open,
  (open) => {
    if (open) resetForm()
  },
)

watch(title, () => (titleError.value = ''))

const createCollectionAction = useAdminAction('catalog.create_collection')
function addCollection() {
  dialog.prompt({
    title: __('New collection'),
    message: __('Collections group products in your store, like T-shirts or Candles.'),
    fields: [{ name: 'title', label: __('Name'), required: true }],
    confirmLabel: __('Add collection'),
    onConfirm: async ({ values }) => {
      const created = await trySubmit(createCollectionAction, { title: values.title })
      if (!created) return
      await collectionsRequest.reload()
      collection.value = createCollectionAction.data.name
    },
  })
}

// The option axis is any attribute catalog.get_attributes marks as one: never Size, which is the
// fixed second axis (generate_variants() depends on that exact spelling), nor the hidden placeholder.
const attributesRequest = useAdminRead('catalog.get_attributes')
const optionAttributeOptions = computed(() =>
  (attributesRequest.data ?? []).filter((a) => a.is_option).map((a) => ({ label: a.name, value: a.name })),
)

const createAttributeAction = useAdminAction('catalog.create_attribute')
function addAttribute() {
  dialog.prompt({
    title: __('New option'),
    message: __('Adds an option every product in your store can use.'),
    fields: [
      { name: 'title', label: __('Name'), required: true, placeholder: __('Material') },
      { name: 'values', label: __('Values'), placeholder: __('Cotton, Linen') },
    ],
    confirmLabel: __('Add option'),
    onConfirm: async ({ values }) => {
      const created = await trySubmit(createAttributeAction, {
        name: values.title,
        values: values.values || undefined,
      })
      if (!created) return
      await attributesRequest.reload()
      optionAttribute.value = values.title
    },
  })
}

watch(optionAttributeOptions, (options) => {
  if (options.length && !options.some((option) => option.value === optionAttribute.value)) {
    optionAttribute.value = options[0].value
  }
})

// Values picked off one attribute mean nothing on another, and neither do the pairs they were unticked in.
watch(optionAttribute, () => {
  colors.value = []
  excludedPairs.value = []
})

// The exact rows sent to create_product, so the summary counts what will really be created.
const optionSizes = computed(() => newProductOptionSizes(colors.value, sizes.value, excludedPairs.value))
// A colour with no sizes still sells, as one item on the hidden size.
const variantCount = computed(() =>
  optionSizes.value.reduce((total, row) => total + (sizes.value.length ? row.sizes.length : 1), 0),
)

// Every colour sizeless is allowed (each sells as one item). Some sized and some not is a half-filled
// grid, and still the owner forgetting a row — create_product refuses that pairing for the same reason.
const sizelessOptions = computed(() => (sizes.value.length ? optionSizes.value.filter((row) => !row.sizes.length) : []))
const gridError = computed(() =>
  sizelessOptions.value.length
    ? __('{0} has no sizes ticked. Tick one, or remove {0} from {1}.', [sizelessOptions.value[0].option, optionAttribute.value])
    : '',
)

const priceError = computed(() => originalPriceError({ price: price.value, originalPrice: originalPrice.value }))

function countOf(count, one, many) {
  return count === 1 ? one : many
}

// What the owner is about to get, counted the way every other screen counts it: one variant per
// colour × size pair a shopper can buy.
const summary = computed(() => {
  const variants = countOf(variantCount.value, __('1 variant'), __('{0} variants', [variantCount.value]))
  const colorCount = colors.value.length
  const sizeCount = sizes.value.length
  if (colorCount && sizeCount) {
    const values = countOf(colorCount, __('1 {0}', [optionAttribute.value.toLowerCase()]), __('{0} {1} values', [colorCount, optionAttribute.value.toLowerCase()]))
    const colorLabel = optionAttribute.value === 'Color' ? countOf(colorCount, __('1 color'), __('{0} colors', [colorCount])) : values
    const sizeLabel = countOf(sizeCount, __('1 size'), __('{0} sizes', [sizeCount]))
    const unticked = colorCount * sizeCount - variantCount.value
    return unticked
      ? __('{0}: {1} × {2}, {3} unticked', [variants, colorLabel, sizeLabel, unticked])
      : __('{0}: {1} × {2}', [variants, colorLabel, sizeLabel])
  }
  if (colorCount) return __('{0}, one for each {1}', [variants, optionAttribute.value.toLowerCase()])
  if (sizeCount) return __('{0}, one for each size', [variants])
  return ''
})

// Names the option the owner picked (Material, not "color") and only the axes in use.
const optionsHint = computed(() => {
  const option = optionAttribute.value.toLowerCase()
  if (colors.value.length && !sizes.value.length) return __('Each {0} is a variant you sell and stock.', [option])
  if (sizes.value.length && !colors.value.length) return __('Each size is a variant you sell and stock.')
  return __('Each {0} and size pair is a variant you sell and stock.', [option])
})

const createAction = useAdminAction('catalog.create_product')

// The price is required. create_product only writes Item Prices for a rate above zero, so a product
// created without one carries no Item Price row at all and reads as 0 until someone prices it by hand.
// The first thing still missing is named next to the button, so a disabled button is never silent.
const missingReason = computed(() => {
  if (!title.value.trim()) return __('Add a title to continue.')
  if (titleError.value) return __('Change the title to continue.')
  if (!hasPrice(price.value)) return __('Enter a price above zero to continue.')
  if (priceError.value) return __('Fix the original price to continue.')
  if (!collection.value) return __('Pick a collection to continue.')
  // The full sentence already sits under the grid; the footer only says what blocks the button.
  if (gridError.value) return __('Fix the ticked sizes to continue.')
  return ''
})

async function submit() {
  if (missingReason.value || createAction.loading) return
  // Read before the wait: the toast and the jump must name this product, not whatever the form
  // holds by the time the server answers.
  const productTitle = title.value.trim()

  const rates = priceInputRates({ price: price.value, originalPrice: originalPrice.value })
  const added = await trySubmit(createAction, {
    title: productTitle,
    collection: collection.value,
    option_attribute: colors.value.length ? optionAttribute.value : undefined,
    size_attribute: 'Size',
    option_sizes: optionSizes.value,
    price: rates.default_rate,
    sale_price: rates.sale_rate,
  })
  // useAdminAction already toasted the refusal; a taken title also belongs on its field.
  if (!added) {
    if (createAction.error?.type === 'DuplicateEntryError') {
      titleError.value = __('A product with this title already exists.')
    }
    return
  }

  const created = createAction.data
  toast.success(__('"{0}" created', [productTitle]))
  // The dialog cannot be dismissed while this runs, but it can be closed from elsewhere (a route
  // change, the onboarding finishing); then the merchant has moved on and is not pulled back.
  if (!addProduct.open) return
  closeAddProduct()
  router.push(productRoute(created.name))
}
</script>

<template>
  <FormDialog
    v-model:open="addProduct.open"
    :title="__('Add product')"
    :primary-label="__('Add product')"
    :primary-disabled="Boolean(missingReason)"
    :loading="createAction.loading"
    :reason="missingReason"
    :note="__('Saved, but not published yet. You add photos next.')"
    :dismissible="!pickerOpen"
    @submit="submit"
  >
    <div class="space-y-5">
      <FormControl
        v-model="title"
        :label="__('Title')"
        :placeholder="__('Cotton oversized tee')"
        :error="titleError"
        required
      />

      <PriceFields
        v-model:price="price"
        v-model:original-price="originalPrice"
        :original-price-error="priceError"
      />

      <Select
        v-model="collection"
        :label="__('Collection')"
        :description="__('Collections group products in your store, like T-shirts or Candles.')"
        :placeholder="__('Select a collection')"
        :options="collectionOptions"
        :empty-text="__('No collections yet')"
        required
      >
        <template #footer="{ close }">
          <div class="border-t border-outline-gray-1 p-1.5">
            <Button
              class="w-full justify-start"
              variant="ghost"
              icon-left="lucide-plus"
              :label="__('New collection')"
              @click="close(); addCollection()"
            />
          </div>
        </template>
      </Select>

      <Button
        v-if="!showOptions"
        class="-ms-2"
        variant="ghost"
        icon-left="lucide-plus"
        :label="__('Add options like size or color')"
        @click="showOptions = true"
      />

      <section v-else class="space-y-4 rounded-4 border border-outline-gray-1 p-4">
        <div class="flex items-start gap-3">
          <div class="min-w-0 flex-1">
            <h3 class="text-base-semibold text-ink-gray-8">{{ __('Options') }}</h3>
            <p class="mt-0.5 text-p-sm text-ink-gray-5">
              {{ optionsHint }}
            </p>
          </div>
          <Button variant="ghost" :label="__('Remove')" @click="clearOptions" />
        </div>

        <div v-if="showOtherOptions" class="flex items-end gap-2">
          <Select
            v-model="optionAttribute"
            class="min-w-0 flex-1"
            :label="__('Option')"
            :options="optionAttributeOptions"
          />
          <Button :label="__('New option')" icon-left="lucide-plus" @click="addAttribute" />
        </div>

        <div>
          <AttributeMultiSelect
            v-model="colors"
            v-model:open="colorsOpen"
            :attribute="optionAttribute"
            :label="optionAttribute"
            :placeholder="__('Pick or type a {0}', [optionAttribute.toLowerCase()])"
            @values="setOptionSwatches"
          />
          <Button
            v-if="!showOtherOptions"
            class="mt-1 -ms-2"
            variant="ghost"
            size="sm"
            icon-left="lucide-arrow-left-right"
            :label="__('Use a different option')"
            @click="showOtherOptions = true"
          />
        </div>

        <AttributeMultiSelect
          v-model="sizes"
          v-model:open="sizesOpen"
          attribute="Size"
          :label="__('Size')"
          :placeholder="__('Pick or type a size')"
        />

        <OptionSizeGrid
          v-if="colors.length && sizes.length"
          v-model="excludedPairs"
          :options="colors"
          :sizes="sizes"
          :option-label="optionAttribute"
          :swatches="optionSwatches"
        />

        <ErrorMessage v-if="gridError" :message="gridError" />
        <p v-else-if="summary" class="text-p-sm text-ink-gray-7">{{ summary }}</p>
      </section>
    </div>
  </FormDialog>
</template>
