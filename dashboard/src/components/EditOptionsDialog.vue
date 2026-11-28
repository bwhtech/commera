<script setup>
import { computed, ref, watch } from 'vue'
import { Alert, Select, toast } from 'frappe-ui'
import { useAdminAction, useAdminRead, trySubmit } from '../data/api'
import { optionChanges, pairKey } from '../data/optionSizes'
import { PLACEHOLDER_ATTRIBUTE, TITLE_MAX_LENGTH, productOptions } from '../data/product'
import { __ } from '../data/translation'
import AttributeMultiSelect from './AttributeMultiSelect.vue'
import FormDialog from './FormDialog.vue'
import OptionSizeGrid from './OptionSizeGrid.vue'

const props = defineProps({ product: { type: Object, required: true } })
const emit = defineEmits(['saved'])
const open = defineModel('open', { type: Boolean, default: false })

const options = ref([])
const sizes = ref([])
const excludedPairs = ref([])
const optionSwatches = ref({})
const optionsOpen = ref(false)
const sizesOpen = ref(false)
const pickerOpen = computed(() => optionsOpen.value || sizesOpen.value)

const firstOption = computed(() => props.product.option_attribute === PLACEHOLDER_ATTRIBUTE)
const hasOptions = computed(() => {
  const shown = productOptions(props.product)
  return Boolean(shown.options.length || shown.sizes.length)
})
const chosenAttribute = ref('')
const attributesRequest = useAdminRead('catalog.get_attributes', { immediate: false })
const attributeOptions = computed(() =>
  (attributesRequest.data ?? [])
    .filter((attribute) => attribute.is_option)
    .map((attribute) => ({ label: attribute.name, value: attribute.name })),
)
const optionLabel = computed(() =>
  firstOption.value ? chosenAttribute.value || __('Option') : props.product.option_attribute || __('Option'),
)

const liveList = computed(() =>
  props.product.variants.flatMap((variant) => variant.sizes.map((size) => ({ option: variant.option, size: size.size }))),
)
const livePairs = computed(() => new Set(liveList.value.map((pair) => pairKey(pair.option, pair.size))))

watch(open, async (isOpen) => {
  if (!isOpen) return
  const shown = productOptions(props.product)
  options.value = shown.options
  sizes.value = shown.sizes
  excludedPairs.value = options.value.flatMap((option) =>
    sizes.value.map((size) => pairKey(option, size)).filter((key) => !livePairs.value.has(key)),
  )
  if (!firstOption.value) return
  await attributesRequest.reload()
  const names = attributeOptions.value.map((option) => option.value)
  chosenAttribute.value = names.includes('Color') ? 'Color' : (names[0] ?? '')
})

watch(chosenAttribute, () => {
  options.value = []
  excludedPairs.value = []
})

function setOptionSwatches(values) {
  optionSwatches.value = Object.fromEntries(
    values.map((entry) => [entry.value, { color: entry.color, image: entry.image }]),
  )
}

const changes = computed(() =>
  optionChanges({
    live: liveList.value,
    options: options.value,
    sizes: sizes.value,
    excluded: excludedPairs.value,
    keepsHiddenOption: firstOption.value,
  }),
)
const addedCount = computed(() => changes.value.added.length)
const removedCount = computed(() => changes.value.removed.length)
const switchesOption = computed(() => firstOption.value && Boolean(options.value.length))

// Whole sentences, like every other line in the dialog, so each half ends with its own period.
const summary = computed(() => {
  const parts = []
  if (addedCount.value === 1) parts.push(__('1 variant will be added.'))
  else if (addedCount.value) parts.push(__('{0} variants will be added.', [addedCount.value]))
  if (removedCount.value === 1) parts.push(__('1 will leave the store.'))
  else if (removedCount.value) parts.push(__('{0} will leave the store.', [removedCount.value]))
  return parts.join(' ')
})

const emptyError = computed(() => (changes.value.ticked.length ? '' : __('Keep at least one variant ticked.')))
const hasChanges = computed(() => Boolean(addedCount.value || removedCount.value))
// Each value gets a page named "<product> - <value>" and an option switch a list named "<product>
// <option>", in 140-character columns: a product named near the limit leaves little room. Said here,
// as save_product_options refuses it, instead of as a failed save.
const nameError = computed(() => {
  const room = TITLE_MAX_LENGTH - props.product.id.length
  if (switchesOption.value && ` ${chosenAttribute.value}`.length > room) {
    return __("This product's name is too long to switch to {0}.", [chosenAttribute.value])
  }
  const tooLong = options.value.find((option) => ` - ${option}`.length > room)
  return tooLong ? __('“{0}” is too long for this product. Use {1} characters or fewer.', [tooLong, room - 3]) : ''
})
const canSave = computed(() => hasChanges.value && !emptyError.value && !nameError.value)
const blockedReason = computed(() =>
  hasChanges.value ? emptyError.value || nameError.value : __('Nothing has changed yet.'),
)

// What saving does, in one quiet paragraph under the summary rather than a stack of alerts.
const consequenceHint = computed(() =>
  [
    removedCount.value &&
      __('Unticked variants leave the store but are not deleted: past orders keep them, and ticking one again brings it back with its stock and price.'),
    addedCount.value &&
      __('A new size takes the price of its {0}. A new {0} takes the product price and starts as not published.', [
        optionLabel.value.toLowerCase(),
      ]),
  ]
    .filter(Boolean)
    .join(' '),
)

const currentStock = computed(() =>
  props.product.variants.reduce((total, variant) => total + variant.sizes.reduce((sum, size) => sum + (size.stock ?? 0), 0), 0),
)
// Shown from the start, not once values are ticked: the seller should know the cost before choosing.
const firstOptionHint = computed(() =>
  currentStock.value
    ? __(
        'The current item goes off sale and keeps its {0} in stock and its past orders. The new variants start with no stock: use Add stock after saving.',
        [currentStock.value],
      )
    : __('The current item goes off sale and keeps its past orders. The new variants start with no stock.'),
)

const saveAction = useAdminAction('catalog.save_product_options')

async function save() {
  if (!canSave.value) return

  const saved = await trySubmit(saveAction, {
    item_template: props.product.id,
    add: changes.value.added,
    remove: changes.value.removed,
    option_attribute: switchesOption.value ? chosenAttribute.value : undefined,
  })
  if (!saved) return

  const { created, disabled, restored } = saveAction.data
  const parts = [
    created && __('{0} added', [created]),
    restored && __('{0} back in the store', [restored]),
    disabled && __('{0} taken out of the store', [disabled]),
  ].filter(Boolean)
  toast.success(__('Variants updated: {0}', [parts.join(', ')]))
  open.value = false
  emit('saved')
}
</script>

<template>
  <FormDialog
    v-model:open="open"
    :title="hasOptions ? __('Edit options') : __('Add options')"
    :primary-label="__('Save changes')"
    :primary-disabled="!canSave"
    :reason="canSave ? '' : blockedReason"
    :loading="saveAction.loading"
    :dismissible="!pickerOpen"
    :dirty="hasChanges"
    @submit="save"
  >
    <div class="space-y-5">
      <!-- Amber: saving takes the item the seller sells today off sale. -->
      <Alert
        v-if="firstOption && (!hasOptions || options.length)"
        theme="amber"
        :title="__('Adding options replaces the current item')"
        :description="firstOptionHint"
      />

      <Select
        v-if="firstOption"
        v-model="chosenAttribute"
        :label="__('Option')"
        :options="attributeOptions"
        :description="__('Like color or material. Sizes are picked below.')"
      />

      <AttributeMultiSelect
        v-if="!firstOption || chosenAttribute"
        v-model="options"
        v-model:open="optionsOpen"
        :attribute="optionLabel"
        :label="optionLabel"
        :placeholder="__('Pick or type a {0}', [optionLabel.toLowerCase()])"
        :description="__('Type a new {0} to add it.', [optionLabel.toLowerCase()])"
        @values="setOptionSwatches"
      />

      <AttributeMultiSelect
        v-model="sizes"
        v-model:open="sizesOpen"
        attribute="Size"
        :label="__('Size')"
        :placeholder="__('Pick or type a size')"
      />

      <OptionSizeGrid
        v-if="options.length && sizes.length"
        v-model="excludedPairs"
        :options="options"
        :sizes="sizes"
        :option-label="optionLabel"
        :swatches="optionSwatches"
        :live="[...livePairs]"
      />

      <div v-if="summary" class="space-y-1">
        <p class="text-p-sm text-ink-gray-7 tabular-nums">{{ summary }}</p>
        <p v-if="!firstOption && consequenceHint" class="text-p-sm text-ink-gray-6">{{ consequenceHint }}</p>
      </div>
    </div>
  </FormDialog>
</template>
