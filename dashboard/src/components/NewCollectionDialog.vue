<script setup>
/**
 * "New collection", opened over Add product and over the import's Match columns step. A FormDialog,
 * so it is a sheet on a phone and asks before dropping a typed name. A taken name is said under Name
 * with the text selected, like a taken product title, instead of in a toast over the buttons.
 */
import { nextTick, ref, watch } from 'vue'
import { FormControl, toast } from 'frappe-ui'
import FormDialog from './FormDialog.vue'
import { trySubmit, useAdminAction } from '../data/api'
import { errorMessage } from '../data/errors'
import { __ } from '../data/translation'

defineProps({
  // Where focus goes after the dialog closes: the control that opened it may be gone by then (a
  // Select's footer button leaves with its list).
  returnFocus: { type: Function, default: null },
})

const open = defineModel('open', { type: Boolean, required: true })
// The new collection's name, once it is created and the dialog has closed.
const emit = defineEmits(['created'])

// Quiet: a taken name is said once, under Name. Every other refusal still gets its one toast.
const createAction = useAdminAction('catalog.create_collection', {
  quiet: true,
  onError: (error) => {
    if (error?.type !== 'DuplicateEntryError') toast.error(errorMessage(error))
  },
})

const title = ref('')
const error = ref('')
const nameField = ref(null)

watch(open, (isOpen) => {
  if (!isOpen) return
  title.value = ''
  error.value = ''
})
watch(title, () => (error.value = ''))

async function save() {
  const name = title.value.trim()
  if (!name || createAction.loading) return
  if (await trySubmit(createAction, { title: name })) {
    open.value = false
    emit('created', createAction.data.name)
    return
  }
  if (createAction.error?.type !== 'DuplicateEntryError') return
  error.value = errorMessage(createAction.error)
  await nextTick()
  const input = nameField.value?.querySelector('input')
  input?.focus()
  input?.select()
}
</script>

<template>
  <FormDialog
    v-model:open="open"
    size="md"
    :title="__('New collection')"
    :description="__('Collections group products in your store, like Shirts or Candles.')"
    :primary-label="__('Add collection')"
    :primary-disabled="!title.trim()"
    :reason="title.trim() ? '' : __('Enter a name to continue.')"
    :loading="createAction.loading"
    :dirty="Boolean(title.trim())"
    :return-focus="returnFocus"
    @submit="save"
  >
    <div ref="nameField">
      <FormControl v-model="title" :label="__('Name')" :error="error" required @keydown.enter.prevent="save" />
    </div>
  </FormDialog>
</template>
