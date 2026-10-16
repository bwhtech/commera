<script setup>
import { computed, ref } from 'vue'
import { Button, Dialog, Switch, TabButtons, Textarea, TextInput } from 'frappe-ui'
import { BUILDER_PAGES, BUILDER_TEMPLATES, builderUrl } from '../theme/builder.js'
import { openBuilder } from './openBuilder.js'

// Creating a free-form page hands off to Frappe Builder. Commera decides the
// starting point (AI prompt, template, blank) and the layout; Builder does
// the rest. The prompt and template reach Builder through the proposed hooks.
const open = defineModel('open', { type: Boolean, default: false })
const emit = defineEmits(['created'])

const mode = ref('ai')
const title = ref('')
const prompt = ref('')
const template = ref('campaign')
const useStoreLayout = ref(true)

const slug = computed(() => title.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''))
const canCreate = computed(() => slug.value && (mode.value !== 'ai' || prompt.value.trim()))

function create() {
  const page = {
    name: slug.value,
    title: title.value.trim(),
    route: `/en/${slug.value}`,
    status: 'Draft',
    edited: 'just now by you',
    layout: useStoreLayout.value ? 'commera-theme' : 'none',
    components: [],
  }
  BUILDER_PAGES.push(page)
  openBuilder(
    builderUrl('new-page', {
      template: mode.value === 'template' ? template.value : undefined,
      prompt: mode.value === 'ai' ? prompt.value.trim() : undefined,
      layout: page.layout,
    }),
    page.title,
  )
  emit('created', page)
  open.value = false
  title.value = ''
  prompt.value = ''
}
</script>

<template>
  <Dialog v-model:open="open" title="New page" size="xl">
    <div class="space-y-4" data-new-page-dialog>
      <TabButtons
        v-model="mode"
        :options="[
          { value: 'ai', label: 'Describe it', iconLeft: 'lucide-sparkles' },
          { value: 'template', label: 'From a template', iconLeft: 'lucide-layout-template' },
          { value: 'blank', label: 'Blank', iconLeft: 'lucide-file' },
        ]"
      />

      <div class="space-y-1.5">
        <label class="text-sm text-ink-gray-7">Page title</label>
        <TextInput v-model="title" placeholder="Winter drop" data-new-page-title />
        <p v-if="slug" class="text-sm text-ink-gray-5">Lives at /en/{{ slug }} and /ar/{{ slug }}</p>
      </div>

      <div v-if="mode === 'ai'" class="space-y-1.5">
        <label class="text-sm text-ink-gray-7">What should the page do?</label>
        <Textarea
          v-model="prompt"
          :rows="4"
          placeholder="A landing page for our winter hoodie drop: big hero, a countdown to Friday, the Hoodies collection, and a short story about the fabric."
          data-new-page-prompt
        />
        <p class="text-sm text-ink-gray-5">Builder's AI drafts the page with your store's collections and Commera components; you refine it in Builder.</p>
      </div>

      <div v-else-if="mode === 'template'" class="grid grid-cols-3 gap-2">
        <button
          v-for="option in BUILDER_TEMPLATES"
          :key="option.value"
          class="rounded border p-3 text-left"
          :class="option.value === template ? 'border-outline-gray-5 bg-surface-gray-2' : 'border-outline-gray-2 hover:border-outline-gray-3'"
          @click="template = option.value"
        >
          <span :class="option.icon" class="size-4 text-ink-gray-6" aria-hidden="true" />
          <span class="mt-2 block text-base font-medium text-ink-gray-9">{{ option.label }}</span>
          <span class="block text-sm text-ink-gray-5">{{ option.description }}</span>
        </button>
      </div>

      <Switch
        v-model="useStoreLayout"
        label="Use the store's header and footer"
        description="The page shows inside your theme's header and footer, which you keep editing in the theme editor."
      />
    </div>

    <template #actions>
      <div class="flex justify-end gap-2">
        <Button label="Cancel" @click="open = false" />
        <Button variant="solid" icon-left="lucide-external-link" label="Create in Builder" :disabled="!canCreate" data-create-in-builder @click="create" />
      </div>
    </template>
  </Dialog>
</template>
