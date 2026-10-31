<script setup>
/**
 * One docfield, as the control its fieldtype asks for. Every settings screen that renders fields
 * it did not hardcode reaches this through SettingsFieldRows, so a provider's API key, an
 * analytics pixel id and an advanced setting all behave the same way.
 */
import { computed, ref } from 'vue'
import { Button, Select, Switch, Textarea, TextInput, toast, useFileUpload } from 'frappe-ui'
import SettingsCollectionControl from './SettingsCollectionControl.vue'
import SettingsLinkControl from './SettingsLinkControl.vue'
import SettingsProductsControl from './SettingsProductsControl.vue'

const NUMERIC_FIELDTYPES = ['Int', 'Float', 'Currency', 'Percent']
const MULTILINE_FIELDTYPES = ['Small Text', 'Text', 'Long Text', 'Text Editor', 'Code']
const ATTACH_FIELDTYPES = ['Attach', 'Attach Image']

const props = defineProps({
  field: { type: Object, required: true },
  modelValue: { type: [String, Number, Boolean, Array], default: null },
  // Only set where the server offers a picker for this doctype's Link fields. Without one a
  // Link stays a plain box rather than a combobox that can never fill itself.
  linkOptionsPath: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})

// `update:modelValue` is every edit, including each keystroke; `change` is the value settled —
// a switch flipped, a file uploaded, a box left. A screen that saves on its own listens to the
// second one, so a half-typed key is never written.
const emit = defineEmits(['update:modelValue', 'change'])

function commit(value) {
  emit('update:modelValue', value)
  emit('change', value)
}

const { upload, isUploading } = useFileUpload()
const fileInput = ref(null)

// Frappe answers with 1/0 and numbers where an input wants a string, and a field never touched
// arrives as null.
const text = computed({
  get: () => (props.modelValue === null || props.modelValue === undefined ? '' : String(props.modelValue)),
  set: (value) => emit('update:modelValue', value),
})

const checked = computed(() => Boolean(props.modelValue) && props.modelValue !== '0')

function commitText(value) {
  if (!NUMERIC_FIELDTYPES.includes(props.field.fieldtype)) return commit(value)
  commit(value === '' ? null : Number(value))
}

function inputType(field) {
  if (field.is_secret) return 'password'
  if (NUMERIC_FIELDTYPES.includes(field.fieldtype)) return 'number'
  return 'text'
}

function selectOptions(field) {
  return (field.options ?? '')
    .split('\n')
    .filter(Boolean)
    .map((value) => ({ label: field.option_labels?.[value] ?? value, value }))
}

async function uploadFile(event) {
  const [file] = [...(event.target.files ?? [])]
  event.target.value = ''
  if (!file) return

  try {
    // Public: these end up in storefront markup — share images, logos — not behind a login.
    const uploaded = await upload(file, { private: false })
    commit(uploaded.file_url)
  } catch {
    toast.error(`Could not upload ${file.name}`)
  }
}
</script>

<template>
  <Switch
    v-if="field.fieldtype === 'Check'"
    :model-value="checked"
    size="sm"
    :disabled="disabled"
    @update:model-value="commit"
  />

  <div v-else-if="field.fieldtype === 'Color'" class="flex w-full items-center gap-2 sm:w-72">
    <input
      :value="text"
      type="color"
      class="size-7 shrink-0 cursor-pointer rounded-4 border border-outline-gray-2 bg-surface-base"
      :disabled="disabled"
      :aria-label="field.label"
      @input="emit('update:modelValue', $event.target.value)"
      @change="commit($event.target.value)"
    />
    <TextInput
      v-model="text"
      class="min-w-0 flex-1"
      :disabled="disabled"
      :aria-label="`${field.label} hex`"
      placeholder="#000000"
      @change="commit($event.target.value)"
    />
  </div>

  <Select
    v-else-if="field.fieldtype === 'Select'"
    :model-value="text"
    class="w-full sm:w-72"
    :options="selectOptions(field)"
    :disabled="disabled"
    @update:model-value="commit"
  />

  <SettingsCollectionControl
    v-else-if="field.fieldtype === 'Collection'"
    :model-value="text"
    :disabled="disabled"
    @update:model-value="commit"
  />

  <SettingsProductsControl
    v-else-if="field.fieldtype === 'Products'"
    :model-value="modelValue ?? []"
    :max="field.max_products"
    :disabled="disabled"
    @update:model-value="commit"
  />

  <SettingsLinkControl
    v-else-if="field.fieldtype === 'Link' && linkOptionsPath"
    :field="field"
    :model-value="text"
    :options-path="linkOptionsPath"
    :disabled="disabled"
    @update:model-value="commit"
  />

  <div v-else-if="ATTACH_FIELDTYPES.includes(field.fieldtype)" class="flex w-full items-center gap-2 sm:w-72">
    <input
      ref="fileInput"
      type="file"
      class="hidden"
      :accept="field.fieldtype === 'Attach Image' ? 'image/*' : undefined"
      @change="uploadFile"
    />
    <p v-if="text" class="min-w-0 flex-1 truncate text-base text-ink-gray-7">{{ text }}</p>
    <p v-else class="min-w-0 flex-1 text-base text-ink-gray-5">Nothing uploaded</p>
    <Button :loading="isUploading" :disabled="disabled" label="Upload" @click="fileInput.click()" />
    <Button
      v-if="text"
      icon="lucide-x"
      variant="ghost"
      :disabled="disabled"
      :aria-label="`Remove ${field.label}`"
      @click="commit('')"
    />
  </div>

  <Textarea
    v-else-if="MULTILINE_FIELDTYPES.includes(field.fieldtype)"
    v-model="text"
    class="w-full sm:w-72"
    :rows="field.fieldtype === 'Code' ? 8 : 3"
    :placeholder="field.placeholder"
    :disabled="disabled"
    @change="commit($event.target.value)"
  />

  <TextInput
    v-else
    v-model="text"
    class="w-full sm:w-72"
    :type="inputType(field)"
    :placeholder="field.is_secret && field.is_set ? '••••••••' : (field.placeholder ?? '')"
    :disabled="disabled"
    @change="commitText($event.target.value)"
  />
</template>
