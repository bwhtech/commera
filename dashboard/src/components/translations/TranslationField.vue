<script setup>
import { computed, ref } from 'vue'
import { Button, FormControl, toast, useFileUpload } from 'frappe-ui'
import { Editor, EditorContent, RichTextKit } from 'frappe-ui/editor'
import RichTextField from '../RichTextField.vue'
import StatusBadge from '../StatusBadge.vue'
import Thumb from '../Thumb.vue'
import { __ } from '../../data/translation'

// One field of one record: its source and its translation, side by side. The editor holds
// unsaved values until Save, so this only reports changes.
const props = defineProps({
  // { field, label, kind, source, value, status }
  field: { type: Object, required: true },
  // { code, name, direction }
  language: { type: Object, required: true },
  sourceLanguage: { type: Object, required: true },
  recordTitle: { type: String, required: true },
  // The unsaved value, or undefined when there is none.
  pending: { type: String, default: undefined },
})
const emit = defineEmits(['change'])

const isUnsaved = computed(() => props.pending !== undefined)
const status = computed(() => (isUnsaved.value ? 'unsaved' : props.field.status))
const value = computed({
  get: () => props.pending ?? props.field.value,
  set: (newValue) => emit('change', newValue),
})
const inputLabel = computed(() => __('{0} of {1} in {2}', [props.field.label, props.recordTitle, props.language.name]))

const { upload } = useFileUpload()
const imageInput = ref(null)
const isUploading = ref(false)

async function swapImage(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  isUploading.value = true
  try {
    // Public: the storefront shows it to shoppers.
    const uploaded = await upload(file, { private: false })
    emit('change', uploaded.file_url)
  } catch {
    toast.error(__('Could not upload {0}', [file.name]))
  } finally {
    isUploading.value = false
  }
}
</script>

<template>
  <div class="grid grid-cols-1 sm:grid-cols-[11rem_minmax(0,1fr)_minmax(0,1fr)]">
    <div class="px-4 pt-3 sm:py-3">
      <p class="text-base text-ink-gray-8">{{ field.label }}</p>
      <StatusBadge v-if="status !== 'current'" class="mt-1.5" :status="status" />
    </div>

    <div class="min-w-0 bg-surface-gray-1 px-4 py-3" :dir="sourceLanguage.direction">
      <div v-if="field.kind === 'image'" class="flex items-center gap-2 text-sm text-ink-gray-7">
        <Thumb :image="field.source" />
        <span class="truncate">{{ field.source }}</span>
      </div>
      <!-- Read-only rich text, so the source's markup renders instead of showing as tags. -->
      <Editor v-else-if="field.kind === 'html'" :model-value="field.source" :extensions="[RichTextKit]" :editable="false">
        <EditorContent class="text-p-base text-ink-gray-7" />
      </Editor>
      <p v-else class="whitespace-pre-wrap break-words text-p-base text-ink-gray-7">{{ field.source }}</p>
      <!-- The store keeps a hash of the old source, not its text, so there is no "Was:" to show. -->
      <p v-if="field.status === 'outdated' && !isUnsaved" class="mt-1.5 text-p-sm text-ink-amber-7">
        {{ __('Source changed') }}
      </p>
    </div>

    <div class="min-w-0 px-4 py-3">
      <div v-if="field.kind === 'image'" class="flex items-center gap-2">
        <Thumb v-if="value" :image="value" />
        <span v-if="value" class="min-w-0 flex-1 truncate text-sm text-ink-gray-8">{{ value }}</span>
        <span v-else class="min-w-0 flex-1 text-sm text-ink-gray-5">
          {{ __('Uses the {0} image', [sourceLanguage.name]) }}
        </span>
        <input ref="imageInput" type="file" accept="image/*" class="hidden" @change="swapImage" />
        <Button size="sm" :label="__('Change')" :loading="isUploading" @click="imageInput.click()" />
        <Button v-if="value" size="sm" variant="ghost" :label="__('Reset')" @click="emit('change', '')" />
      </div>
      <div v-else :dir="language.direction">
        <RichTextField v-if="field.kind === 'html'" v-model="value" min-height="min-h-32" />
        <FormControl
          v-else
          v-model="value"
          :type="field.kind === 'long' ? 'textarea' : 'text'"
          :rows="field.kind === 'long' ? 3 : undefined"
          :aria-label="inputLabel"
        />
      </div>
      <!-- Saving the same text stamps it with the source as it is now, which clears outdated. -->
      <Button
        v-if="field.status === 'outdated' && !isUnsaved"
        class="mt-1.5"
        size="sm"
        variant="ghost"
        icon-left="lucide-check"
        :label="__('Still correct')"
        @click="emit('change', field.value)"
      />
    </div>
  </div>
</template>
