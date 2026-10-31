<script setup>
import { computed, ref } from 'vue'
import { Button, Dialog, TextInput, toast } from 'frappe-ui'
import { START_OPTIONS, pages } from './data.js'

// Variations A and B: a page is always designed in Builder, so the only
// questions are its name and how to start. Variation C first asks what kind
// of page it is (askKind), because text pages stay in the dashboard.
const props = defineProps({ askKind: { type: Boolean, default: false } })
const open = defineModel('open', { type: Boolean, default: false })

const kind = ref(props.askKind ? null : 'designed')
const title = ref('')
const start = ref('blank')
const slug = computed(() => title.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''))

function create() {
  pages.unshift({ name: slug.value, title: title.value.trim(), route: `/${slug.value}`, status: 'Draft', kind: kind.value, edited: 'Just now' })
  toast.success(kind.value === 'text' ? 'Page created' : 'Opening Frappe Builder…')
  open.value = false
  title.value = ''
  kind.value = props.askKind ? null : 'designed'
}
</script>

<template>
  <Dialog v-model:open="open" title="New page" size="lg">
    <div class="space-y-5" data-new-page>
      <div v-if="askKind" class="grid grid-cols-2 gap-3">
        <button
          v-for="option in [
            { value: 'text', icon: 'lucide-file-text', label: 'Text page', text: 'About us, FAQ, policies. Write it like a document, right here.' },
            { value: 'designed', icon: 'lucide-palette', label: 'Designed page', text: 'Campaigns and landing pages. Lay it out visually in Frappe Builder.' },
          ]"
          :key="option.value"
          class="rounded-lg border p-4 text-left"
          :class="kind === option.value ? 'border-outline-gray-5 bg-surface-gray-2' : 'border-outline-gray-2 hover:border-outline-gray-3'"
          :data-kind="option.value"
          @click="kind = option.value"
        >
          <span :class="option.icon" class="size-5 text-ink-gray-7" aria-hidden="true" />
          <span class="mt-3 block text-base font-semibold text-ink-gray-9">{{ option.label }}</span>
          <span class="mt-1 block text-sm text-ink-gray-6">{{ option.text }}</span>
        </button>
      </div>

      <template v-if="kind">
        <div class="space-y-1.5">
          <label class="text-sm text-ink-gray-7">Page name</label>
          <TextInput v-model="title" placeholder="Winter sale" data-page-title />
          <p v-if="slug" class="text-sm text-ink-gray-5">yourstore.com/{{ slug }}</p>
        </div>

        <div v-if="kind === 'designed'" class="space-y-1.5">
          <label class="text-sm text-ink-gray-7">Start from</label>
          <div class="grid grid-cols-3 gap-2">
            <button
              v-for="option in START_OPTIONS"
              :key="option.value"
              class="rounded border p-3 text-left"
              :class="start === option.value ? 'border-outline-gray-5 bg-surface-gray-2' : 'border-outline-gray-2 hover:border-outline-gray-3'"
              @click="start = option.value"
            >
              <span :class="option.icon" class="size-4 text-ink-gray-6" aria-hidden="true" />
              <span class="mt-2 block text-sm font-medium text-ink-gray-9">{{ option.label }}</span>
              <span class="block text-xs text-ink-gray-5">{{ option.description }}</span>
            </button>
          </div>
          <p class="text-sm text-ink-gray-5">Your store's header, footer, colours and fonts are added automatically.</p>
        </div>
      </template>
    </div>

    <template #actions>
      <div class="flex justify-end gap-2">
        <Button label="Cancel" @click="open = false" />
        <Button
          variant="solid"
          :label="kind === 'designed' ? 'Create and open Builder' : 'Create page'"
          :icon-right="kind === 'designed' ? 'lucide-arrow-up-right' : undefined"
          :disabled="!kind || !slug"
          data-create
          @click="create"
        />
      </div>
    </template>
  </Dialog>
</template>
