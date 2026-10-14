<script setup>
import { computed, ref, watch } from 'vue'
import { Alert, Button, Dialog, ErrorMessage, toast } from 'frappe-ui'
import { useAdminAction } from '../data/api'
import { buildOptionSizes, pairKey } from '../data/optionSizes'
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
  if (addedCount.value) parts.push(`${addedCount.value} ${addedCount.value === 1 ? 'variant' : 'variants'} will be added`)
  if (removedCount.value) parts.push(`${removedCount.value} will come off sale`)
  return parts.join(' · ') || 'No changes yet'
})

const emptyError = computed(() => (tickedPairs.value.size ? '' : 'Keep at least one variant ticked.'))
const canSave = computed(() => (addedCount.value || removedCount.value) && !emptyError.value)

const saveAction = useAdminAction('catalog.save_product_options')

async function save() {
  if (!canSave.value) return

  try {
    await saveAction.submit({ item_template: props.product.id, add: addedPairs.value, remove: removedPairs.value })
  } catch {
    return
  }

  const { created, disabled, restored } = saveAction.data
  const parts = [
    created && `${created} added`,
    restored && `${restored} back on sale`,
    disabled && `${disabled} taken off sale`,
  ].filter(Boolean)
  toast.success(`Variants updated: ${parts.join(', ')}`)
  open.value = false
  emit('saved')
}
</script>

<template>
  <Dialog v-model:open="open" size="xl" title="Edit options" :dismissible="!pickerOpen">
    <template #default>
      <div class="space-y-5">
        <AttributeMultiSelect
          v-model="options"
          v-model:open="optionsOpen"
          :attribute="optionLabel"
          :label="optionLabel"
          :placeholder="`Pick or type a ${optionLabel.toLowerCase()}`"
          :description="`Type a new ${optionLabel.toLowerCase()} to add it`"
          @values="setOptionSwatches"
        />

        <AttributeMultiSelect
          v-model="sizes"
          v-model:open="sizesOpen"
          attribute="Size"
          label="Sizes"
          placeholder="Pick or type a size"
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
          title="Unticked variants are hidden, not deleted"
          description="They leave the storefront and can't be sold, but past orders keep them. Tick one again to bring it back with its stock and price."
        />
        <Alert
          v-else-if="addedCount"
          title="Prices are filled in for you"
          description="A new size takes its option's price and goes on sale with it. A new option takes the product's price and stays hidden until it has a photo."
        />
      </div>
    </template>

    <template #actions>
      <Button
        class="w-full"
        variant="solid"
        theme="gray"
        label="Save options"
        :disabled="!canSave"
        :loading="saveAction.loading"
        @click="save"
      />
    </template>
  </Dialog>
</template>
