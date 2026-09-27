<script setup>
import { computed, ref } from 'vue'
import { Button, Dialog, Textarea, TextInput, toast } from 'frappe-ui'
import { BUILDER_THEME_PAGES, liveTheme, themes } from './data.js'

// Creating a Builder theme creates a draft theme in Commera, flagged as a
// Builder theme, plus one empty Builder page per theme page. Nothing goes
// live until the merchant publishes it from Themes.
const open = defineModel('open', { type: Boolean, default: false })
const emit = defineEmits(['created'])

const title = ref('')
const start = ref('blank')
const prompt = ref('')
const slug = computed(() => title.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, ''))

const starts = [
  { value: 'blank', label: 'Blank pages', icon: 'lucide-file', text: 'Design each page from scratch' },
  { value: 'ai', label: 'Describe it', icon: 'lucide-sparkles', text: "Builder's AI drafts every page" },
  { value: 'copy', label: `Start from ${liveTheme()?.title ?? 'live theme'}`, icon: 'lucide-copy', text: 'Its colours, fonts and layout' },
]

function create() {
  const theme = {
    name: slug.value,
    title: title.value.trim(),
    kind: 'builder',
    source: 'Made on this site',
    saved: 'Created just now',
    colours: ['#0d9488', '#1e293b'],
    pages: Object.fromEntries(BUILDER_THEME_PAGES.map((page) => [page.key, start.value === 'blank' ? 'empty' : 'draft'])),
    settings: { accent: '#0d9488', text: '#1c1917', background: '#ffffff', heading_font: 'Inter', body_font: 'Inter' },
  }
  themes.push(theme)
  toast.success(`${theme.title} created as a draft theme`)
  open.value = false
  title.value = ''
  prompt.value = ''
  emit('created', theme)
}
</script>

<template>
  <Dialog v-model:open="open" title="Create a theme with Frappe Builder" size="xl">
    <div class="space-y-5" data-create-theme>
      <p class="text-base text-ink-gray-7">
        A Builder theme is a full theme you design visually. It's added to your Draft themes, so your live store doesn't change until you publish it.
      </p>

      <div class="space-y-1.5">
        <label class="text-sm text-ink-gray-7">Theme name</label>
        <TextInput v-model="title" placeholder="Winter 2026" data-theme-name />
      </div>

      <div class="space-y-1.5">
        <label class="text-sm text-ink-gray-7">Start with</label>
        <div class="grid grid-cols-3 gap-2">
          <button
            v-for="option in starts"
            :key="option.value"
            class="rounded border p-3 text-left"
            :class="start === option.value ? 'border-outline-gray-5 bg-surface-gray-2' : 'border-outline-gray-2 hover:border-outline-gray-3'"
            @click="start = option.value"
          >
            <span :class="option.icon" class="size-4 text-ink-gray-6" aria-hidden="true" />
            <span class="mt-2 block text-sm font-medium text-ink-gray-9">{{ option.label }}</span>
            <span class="block text-xs text-ink-gray-5">{{ option.text }}</span>
          </button>
        </div>
        <Textarea
          v-if="start === 'ai'"
          v-model="prompt"
          :rows="3"
          placeholder="Calm and minimal, lots of white space, big product photos, a serif for headings."
        />
      </div>

      <div class="rounded border border-outline-gray-2 bg-surface-gray-1 p-3">
        <p class="text-sm font-medium text-ink-gray-8">These pages are created for you to design in Builder</p>
        <ul class="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
          <li v-for="page in BUILDER_THEME_PAGES" :key="page.key" class="flex items-center gap-2 text-sm text-ink-gray-7">
            <span :class="page.icon" class="size-3.5 text-ink-gray-5" aria-hidden="true" />
            {{ page.title }}
          </li>
        </ul>
      </div>
    </div>

    <template #actions>
      <div class="flex justify-end gap-2">
        <Button label="Cancel" @click="open = false" />
        <Button variant="solid" label="Create theme" :disabled="!slug || (start === 'ai' && !prompt.trim())" data-create-theme-submit @click="create" />
      </div>
    </template>
  </Dialog>
</template>
