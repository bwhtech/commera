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
  <!-- Label, gap and description copy FormControl's own (frappe-ui's InputLabel and InputDescription,
       which it does not export), so this field reads as one of the form's fields beside a Title. -->
  <div class="space-y-1.5">
    <p v-if="label" class="text-sm leading-tighter text-ink-gray-6">{{ label }}</p>
    <div
      class="overflow-hidden rounded-4 border border-outline-gray-2 focus-within:border-outline-gray-3"
    >
      <Editor v-model="model" :extensions="[RichTextKit]" :placeholder="placeholder" :editable="!disabled">
        <EditorFixedMenu v-if="!disabled" :items="commentToolbar" class="border-b border-outline-gray-1" />
        <EditorContent :class="['px-3 py-2', minHeight]" />
      </Editor>
    </div>
    <p v-if="description" class="text-p-sm text-ink-gray-6">{{ description }}</p>
  </div>
</template>
