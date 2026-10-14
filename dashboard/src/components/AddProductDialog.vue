<script setup>
/**
 * Create a sellable product in one screen: catalog.create_product does the rest
 * (Item template + variants, Style Attribute Configurator, generate_variants, prices).
 * Company, warehouse, price list, UOM and naming series are resolved server-side —
 * this dialog never shows an ERPNext concept the owner did not ask for.
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Alert, Button, Dialog, ErrorMessage, FormControl, Select, dialog, toast } from 'frappe-ui'
import { useAdminAction, useAdminRead } from '../data/api'
import { addProduct, closeAddProduct } from '../data/addProduct'
import { buildOptionSizes } from '../data/optionSizes'
import { productRoute } from '../ia/routes'
import AttributeMultiSelect from './AttributeMultiSelect.vue'
import OptionSizeGrid from './OptionSizeGrid.vue'

const router = useRouter()

const title = ref('')
const collection = ref('')
const optionAttribute = ref('Color')
const colors = ref([])
const sizes = ref([])
const excludedPairs = ref([])
const compareAt = ref(null)
const price = ref(null)
const colorsOpen = ref(false)
const optionSwatches = ref({})

function setOptionSwatches(values) {
  optionSwatches.value = Object.fromEntries(
    values.map((entry) => [entry.value, { color: entry.color, image: entry.image }]),
  )
}
const sizesOpen = ref(false)

// reka guards only Escape by topmost layer, so one outside click dismisses the
// popover and the dialog both; the dialog yields while a picker owns that click.
const pickerOpen = computed(() => colorsOpen.value || sizesOpen.value)

function resetForm() {
  title.value = ''
  collection.value = ''
  optionAttribute.value = 'Color'
  colors.value = []
  sizes.value = []
  excludedPairs.value = []
  compareAt.value = null
  price.value = null
}

watch(
  () => addProduct.open,
  (open) => {
    if (open) resetForm()
  },
)

const collectionsRequest = useAdminRead('catalog.get_collections')
const collectionOptions = computed(() => [
  { label: 'Select a collection', value: '' },
  ...(collectionsRequest.data ?? []).map((name) => ({ label: name, value: name })),
])

const createCollectionAction = useAdminAction('catalog.create_collection')
function addCollection() {
  dialog.prompt({
    title: 'New collection',
    fields: [{ name: 'title', label: 'Name', required: true }],
    onConfirm: async ({ values }) => {
      try {
        await createCollectionAction.submit({ title: values.title })
      } catch {
        return
      }
      await collectionsRequest.reload()
      collection.value = values.title
      toast.success(`"${values.title}" created`)
    },
  })
}

// The option axis is any attribute EXCEPT Size — Size has to keep that exact spelling
// (generate_variants() depends on it; see catalog.create_product's Trap 2 guard), so it is fixed
// rather than picked. Both axes are optional here: a book has neither, and create_product fills
// them with a hidden value rather than refusing the product.
const attributesRequest = useAdminRead('catalog.get_attributes')
const attributes = computed(() => attributesRequest.data ?? [])
const optionAttributeOptions = computed(() =>
  attributes.value.filter((a) => a.name !== 'Size').map((a) => ({ label: a.name, value: a.name })),
)

const createAttributeAction = useAdminAction('catalog.create_attribute')
function addAttribute() {
  dialog.prompt({
    title: 'New option',
    fields: [
      { name: 'title', label: 'Name', required: true, placeholder: 'Format' },
      { name: 'values', label: 'Values', placeholder: 'Paperback, Hardcover' },
    ],
    onConfirm: async ({ values }) => {
      try {
        await createAttributeAction.submit({ name: values.title, values: values.values || undefined })
      } catch {
        return
      }
      await attributesRequest.reload()
      optionAttribute.value = values.title
      toast.success(`"${values.title}" created`)
    },
  })
}
watch(attributes, (list) => {
  if (!list.some((a) => a.name === optionAttribute.value)) {
    optionAttribute.value = list.find((a) => a.name === 'Color')?.name ?? list.find((a) => a.name !== 'Size')?.name ?? ''
  }
})

// Values picked off one attribute mean nothing on another, and neither do the pairs they were unticked in.
watch(optionAttribute, () => {
  colors.value = []
  excludedPairs.value = []
})

const optionSizes = computed(() => buildOptionSizes(colors.value, sizes.value, excludedPairs.value))
const variantCount = computed(() => optionSizes.value.reduce((total, row) => total + row.sizes.length, 0))

// Every option sizeless is a book, and allowed. Some sized and some not is a half-filled grid, and
// still the owner forgetting a row — create_product refuses that pairing for the same reason.
const sizelessOptions = computed(() => optionSizes.value.filter((row) => !row.sizes.length))
const mixedOption = computed(() =>
  sizelessOptions.value.length && sizelessOptions.value.length < optionSizes.value.length
    ? sizelessOptions.value[0].option
    : '',
)
const gridError = computed(() => (mixedOption.value ? `Pick at least one size for ${mixedOption.value}` : ''))

// A price is required, not optional. create_product only writes Item Prices for a rate
// above zero, so a product created without one carries no Item Price row at all and reads
// as 0 on every screen until someone prices it by hand — it can never be sold in between.
const canSubmit = computed(
  () =>
    Boolean(title.value.trim()) &&
    Boolean(collection.value) &&
    Number(price.value) > 0 &&
    !mixedOption.value,
)

// What the owner is about to get, in their words rather than ERPNext's.
const summary = computed(() => {
  const optionCount = colors.value.length
  const optionWord = optionCount === 1 ? 'option' : 'options'
  if (variantCount.value) {
    const variantWord = variantCount.value === 1 ? 'variant' : 'variants'
    return `${optionCount} ${optionWord} · ${variantCount.value} ${variantWord} will be created`
  }
  if (optionCount) return `${optionCount} ${optionWord} · no sizes, so each one sells as a single item`
  return 'No options — this sells as a single item, the way a book does'
})

const createAction = useAdminAction('catalog.create_product')

// A disabled button with no reason reads as a broken screen, so the first thing still missing is named.
const submitHint = computed(() => {
  if (canSubmit.value || createAction.loading) return ''
  if (!title.value.trim()) return 'Add a title to continue.'
  if (!collection.value) return 'Pick a collection to continue.'
  if (!(Number(price.value) > 0)) return 'Set a price above zero to continue.'
  return ''
})

async function submit() {
  if (!canSubmit.value) return

  try {
    await createAction.submit({
      title: title.value.trim(),
      collection: collection.value,
      option_attribute: colors.value.length ? optionAttribute.value : undefined,
      size_attribute: 'Size',
      option_sizes: optionSizes.value,
      price: compareAt.value || undefined,
      sale_price: price.value || undefined,
    })
  } catch {
    // A failure (missing collection, colliding abbreviation, wrong size attribute…) already
    // toasted inside useAdminAction — the form stays open so the owner can fix it and resubmit.
    return
  }

  const created = createAction.data
  toast.success(`"${title.value}" created`)
  closeAddProduct()
  router.push(productRoute(created.name))
}
</script>

<template>
  <Dialog
    v-model:open="addProduct.open"
    size="xl"
    title="Add product"
    :dismissible="!pickerOpen"
    @update:open="(v) => (v ? null : closeAddProduct())"
  >
    <template #default>
      <div class="space-y-5">
        <FormControl v-model="title" label="Title" placeholder="Cotton oversized tee" required />

        <div>
          <span class="mb-1.5 block text-base text-ink-gray-6">
            Collection
            <span class="text-ink-red-5 select-none" aria-hidden="true">*</span>
            <span class="sr-only">(required)</span>
          </span>
          <div class="flex gap-2">
            <Select v-model="collection" class="min-w-0 flex-1" :options="collectionOptions" />
            <Button label="New" icon-left="lucide-plus" @click="addCollection" />
          </div>
        </div>

        <div>
          <span class="mb-1.5 block text-base text-ink-gray-6">Option</span>
          <div class="flex gap-2">
            <Select v-model="optionAttribute" class="min-w-0 flex-1" :options="optionAttributeOptions" />
            <Button label="New" icon-left="lucide-plus" @click="addAttribute" />
          </div>
          <p class="mt-1.5 text-p-sm text-ink-gray-5">
            What this product varies by. Sizes are added below and apply to every option.
          </p>
        </div>

        <AttributeMultiSelect
          v-if="optionAttribute"
          v-model="colors"
          v-model:open="colorsOpen"
          :attribute="optionAttribute"
          :label="optionAttribute"
          :placeholder="`Pick or type a ${optionAttribute.toLowerCase()}`"
          :description="`Type a new ${optionAttribute.toLowerCase()} to add it — leave empty if this product has none`"
          @values="setOptionSwatches"
        />

        <AttributeMultiSelect
          v-model="sizes"
          v-model:open="sizesOpen"
          attribute="Size"
          label="Sizes"
          placeholder="Pick or type a size"
          description="Leave empty for a product that has no sizes, like a book"
        />

        <OptionSizeGrid
          v-if="colors.length && sizes.length"
          v-model="excludedPairs"
          :options="colors"
          :sizes="sizes"
          :option-label="optionAttribute || 'Option'"
          :swatches="optionSwatches"
        />

        <p class="text-sm text-ink-gray-5">{{ summary }}</p>
        <ErrorMessage :message="gridError" />

        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormControl v-model.number="price" type="number" label="Price *" placeholder="0" />
          <FormControl v-model.number="compareAt" type="number" label="Compare at" placeholder="0" />
        </div>

        <Alert
          title="Photos come next"
          description="This product is created without a photo, so it stays hidden from shoppers until you add one — from the product page, right after this."
        />
      </div>
    </template>

    <template #actions>
      <div class="w-full">
        <Button
          class="w-full"
          variant="solid"
          theme="gray"
          label="Add product"
          :disabled="!canSubmit"
          :loading="createAction.loading"
          @click="submit"
        />
        <p v-if="submitHint" class="mt-2 text-center text-sm text-ink-gray-5">{{ submitHint }}</p>
      </div>
    </template>
  </Dialog>
</template>

