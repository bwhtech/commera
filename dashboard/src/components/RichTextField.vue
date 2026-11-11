<script setup>
import { Editor, EditorContent, EditorFixedMenu, RichTextKit, commentToolbar } from 'frappe-ui/editor'

defineProps({
  disabled: { type: Boolean, default: false },
  label: { type: String, default: '' },
  description: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  minHeight: { type: String, default: 'min-h-24' },
})

const model = defineModel({ type: String, default: '' })
</script>

<template>
  <div>
    <p v-if="label" class="mb-1.5 text-base text-ink-gray-6">{{ label }}</p>
    <div
      class="overflow-hidden rounded-4 border border-outline-gray-2 focus-within:border-outline-gray-3"
    >
      <Editor v-model="model" :extensions="[RichTextKit]" :placeholder="placeholder" :editable="!disabled">
        <EditorFixedMenu v-if="!disabled" :items="commentToolbar" class="border-b border-outline-gray-1" />
        <EditorContent :class="['px-3 py-2', minHeight]" />
      </Editor>
    </div>
    <p v-if="description" class="mt-1.5 text-sm text-ink-gray-5">{{ description }}</p>
  </div>
</template>
