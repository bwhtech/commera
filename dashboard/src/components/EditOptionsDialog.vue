<script setup>
import { computed, ref, watch } from 'vue'
import { Alert, Button, Dialog, ErrorMessage, Select, toast } from 'frappe-ui'
import { useAdminAction, useAdminRead, trySubmit } from '../data/api'
import { optionChanges, pairKey } from '../data/optionSizes'
import { PLACEHOLDER_ATTRIBUTE, productOptions } from '../data/product'
import { __ } from '../data/translation'
import AttributeMultiSelect from './AttributeMultiSelect.vue'
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
const chosenAttribute = ref('')
const attributesRequest = useAdminRead('catalog.get_attributes', { immediate: false })
const attributeOptions = computed(() =>
  (attributesRequest.data ?? [])
    .filter((attribute) => ![PLACEHOLDER_ATTRIBUTE, 'Size'].includes(attribute.name))
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

const summary = computed(() => {
  const parts = []
  if (addedCount.value === 1) parts.push(__('1 variant will be added'))
  else if (addedCount.value) parts.push(__('{0} variants will be added', [addedCount.value]))
  if (removedCount.value) parts.push(__('{0} will come off sale', [removedCount.value]))
  return parts.join(' · ') || __('No changes yet')
})

const emptyError = computed(() => (changes.value.ticked.length ? '' : __('Keep at least one variant ticked.')))
const canSave = computed(() => (addedCount.value || removedCount.value) && !emptyError.value)

const removedHint = __(
  "They leave the storefront and can't be sold, but past orders keep them. Tick one again to bring it back with its stock and price.",
)
const addedHint = __(
  "A new size takes its option's price and goes on sale with it. A new option takes the product's price and stays hidden until it has a photo.",
)

const stockByPair = computed(
  () =>
    new Map(
      props.product.variants.flatMap((variant) =>
        variant.sizes.map((size) => [pairKey(variant.option, size.size), size.stock ?? 0]),
      ),
    ),
)
const offSaleStock = computed(() =>
  changes.value.removed.reduce((total, pair) => total + (stockByPair.value.get(pairKey(pair.option, pair.size)) ?? 0), 0),
)
const firstOptionHint = computed(() =>
  offSaleStock.value
    ? __(
        'The {0} in stock and past orders stay on the current item, which goes off sale. The new variants start with no stock: use Receive stock to add it.',
        [offSaleStock.value],
      )
    : __('Past orders stay on the current item, which goes off sale. The new variants start with no stock.'),
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
    restored && __('{0} back on sale', [restored]),
    disabled && __('{0} taken off sale', [disabled]),
  ].filter(Boolean)
  toast.success(__('Variants updated: {0}', [parts.join(', ')]))
  open.value = false
  emit('saved')
}
</script>

<template>
  <Dialog v-model:open="open" size="xl" :title="__('Edit options')" :dismissible="!pickerOpen">
    <template #default>
      <div class="space-y-5">
        <Select
          v-if="firstOption"
          v-model="chosenAttribute"
          :label="__('Option')"
          :options="attributeOptions"
          :description="__('What this product varies by. Sizes are added below and apply to every option.')"
        />

        <AttributeMultiSelect
          v-if="!firstOption || chosenAttribute"
          v-model="options"
          v-model:open="optionsOpen"
          :attribute="optionLabel"
          :label="optionLabel"
          :placeholder="__('Pick or type a {0}', [optionLabel.toLowerCase()])"
          :description="__('Type a new {0} to add it', [optionLabel.toLowerCase()])"
          @values="setOptionSwatches"
        />

        <AttributeMultiSelect
          v-model="sizes"
          v-model:open="sizesOpen"
          attribute="Size"
          :label="__('Sizes')"
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

        <p class="text-sm text-ink-gray-5">{{ summary }}</p>
        <ErrorMessage :message="emptyError" />

        <Alert
          v-if="firstOption && removedCount && addedCount"
          :title="__('The current item goes off sale')"
          :description="firstOptionHint"
        />
        <Alert
          v-else-if="removedCount"
          :title="__('Unticked variants are hidden, not deleted')"
          :description="removedHint"
        />
        <Alert
          v-else-if="addedCount"
          :title="__('Prices are filled in for you')"
          :description="addedHint"
        />
      </div>
    </template>

    <template #actions>
      <Button
        class="w-full"
        variant="solid"
        theme="gray"
        :label="__('Save options')"
        :disabled="!canSave"
        :loading="saveAction.loading"
        @click="save"
      />
    </template>
  </Dialog>
</template>
