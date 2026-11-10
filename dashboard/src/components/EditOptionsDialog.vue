<script setup>
import { computed, ref, watch } from 'vue'
import { Alert, Button, Dialog, ErrorMessage, toast } from 'frappe-ui'
import { useAdminAction, trySubmit } from '../data/api'
import { buildOptionSizes, pairKey } from '../data/optionSizes'
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

const optionLabel = computed(() => props.product.option_attribute || 'Option')

const liveList = computed(() =>
  props.product.variants.flatMap((variant) => variant.sizes.map((size) => ({ option: variant.option, size: size.size }))),
)
const livePairs = computed(() => new Set(liveList.value.map((pair) => pairKey(pair.option, pair.size))))

watch(open, (isOpen) => {
  if (!isOpen) return
  options.value = [...new Set(props.product.variants.map((variant) => variant.option))]
  sizes.value = [...new Set(props.product.variants.flatMap((variant) => variant.sizes.map((size) => size.size)))]
  excludedPairs.value = options.value.flatMap((option) =>
    sizes.value.map((size) => pairKey(option, size)).filter((key) => !livePairs.value.has(key)),
  )
})

function setOptionSwatches(values) {
  optionSwatches.value = Object.fromEntries(
    values.map((entry) => [entry.value, { color: entry.color, image: entry.image }]),
  )
}

const optionSizes = computed(() => buildOptionSizes(options.value, sizes.value, excludedPairs.value))
const tickedList = computed(() => optionSizes.value.flatMap((row) => row.sizes.map((size) => ({ option: row.option, size }))))
const tickedPairs = computed(() => new Set(tickedList.value.map((pair) => pairKey(pair.option, pair.size))))

const addedPairs = computed(() => tickedList.value.filter((pair) => !livePairs.value.has(pairKey(pair.option, pair.size))))
const removedPairs = computed(() => liveList.value.filter((pair) => !tickedPairs.value.has(pairKey(pair.option, pair.size))))
const addedCount = computed(() => addedPairs.value.length)
const removedCount = computed(() => removedPairs.value.length)

const summary = computed(() => {
  const parts = []
  if (addedCount.value === 1) parts.push(__('1 variant will be added'))
  else if (addedCount.value) parts.push(__('{0} variants will be added', [addedCount.value]))
  if (removedCount.value) parts.push(__('{0} will come off sale', [removedCount.value]))
  return parts.join(' · ') || __('No changes yet')
})

const emptyError = computed(() => (tickedPairs.value.size ? '' : __('Keep at least one variant ticked.')))
const canSave = computed(() => (addedCount.value || removedCount.value) && !emptyError.value)

const removedHint = __(
  "They leave the storefront and can't be sold, but past orders keep them. Tick one again to bring it back with its stock and price.",
)
const addedHint = __(
  "A new size takes its option's price and goes on sale with it. A new option takes the product's price and stays hidden until it has a photo.",
)

const saveAction = useAdminAction('catalog.save_product_options')

async function save() {
  if (!canSave.value) return

  const saved = await trySubmit(saveAction, {
    item_template: props.product.id,
    add: addedPairs.value,
    remove: removedPairs.value,
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
        <AttributeMultiSelect
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
          v-if="removedCount"
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
