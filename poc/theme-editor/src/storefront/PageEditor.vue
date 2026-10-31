<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Select, TabButtons, TextInput, Textarea, toast } from 'frappe-ui'
import {
  Editor, EditorContent, EditorFixedMenu, RichTextKit,
  HeadingGroup, Separator, Bold, Italic, BulletList, OrderedList, Blockquote, InsertLink, InsertImage, InsertTable,
} from 'frappe-ui/editor'
import StorefrontShell from './StorefrontShell.vue'
import { contentPages, liveTheme, templatesFor } from './data.js'

const route = useRoute()
const router = useRouter()
const page = computed(() => contentPages.find((candidate) => candidate.name === route.params.page))
const theme = computed(liveTheme)
const language = ref('en')

// Commera is bilingual: the Arabic text is a sibling field (content_ar), and an
// empty Arabic page falls back to English on the /ar storefront.
const content = computed({
  get: () => (language.value === 'ar' ? page.value.content_ar : page.value.content),
  set: (value) => (page.value[language.value === 'ar' ? 'content_ar' : 'content'] = value),
})

const extensions = [RichTextKit]
const toolbar = [HeadingGroup, Separator, Bold, Italic, Separator, BulletList, OrderedList, Blockquote, Separator, InsertLink, InsertImage, InsertTable]

function save() {
  page.value.updated = 'Just now'
  toast.success('Page saved')
}
</script>

<template>
  <StorefrontShell>
    <template #bare>
      <div v-if="page" class="mx-auto max-w-5xl px-8 py-10" data-page-editor>
        <button class="mb-3 flex items-center gap-1 text-sm text-ink-gray-5 hover:text-ink-gray-7" @click="router.push('/storefront/pages')">
          <span class="lucide-chevron-left size-3.5" aria-hidden="true" /> Pages
        </button>
        <div class="flex items-center gap-3">
          <h1 class="min-w-0 flex-1 truncate text-2xl font-semibold text-ink-gray-9">{{ page.title || 'Untitled page' }}</h1>
          <Button label="Preview" icon-left="lucide-eye" @click="toast.info(`Opens /${page.name} in ${theme.title}`)" />
          <Button variant="solid" label="Save" @click="save" />
        </div>

        <div class="mt-6 grid grid-cols-[1fr_18rem] gap-6">
          <div class="min-w-0 space-y-4">
            <div class="space-y-1.5">
              <label class="text-sm text-ink-gray-7">Title</label>
              <TextInput v-model="page.title" placeholder="About us" />
            </div>
            <div class="space-y-1.5">
              <div class="flex items-center justify-between">
                <label class="text-sm text-ink-gray-7">Content</label>
                <TabButtons v-model="language" :options="[{ value: 'en', label: 'English' }, { value: 'ar', label: 'العربية' }]" />
              </div>
              <Editor :key="language" v-model="content" :extensions="extensions" :placeholder="language === 'ar' ? 'Empty: the English text is shown on the Arabic store' : 'Write your page…'">
                <template #default>
                  <div class="overflow-hidden rounded-lg border border-outline-gray-2" :dir="language === 'ar' ? 'rtl' : 'ltr'">
                    <div class="border-b border-outline-gray-1 px-2 py-1.5"><EditorFixedMenu :items="toolbar" class="flex-wrap" /></div>
                    <EditorContent class="min-h-72 px-5 py-4 text-ink-gray-8" />
                  </div>
                </template>
              </Editor>
            </div>
          </div>

          <div class="space-y-4">
            <div class="rounded-lg border border-outline-gray-2 p-4">
              <p class="text-sm font-medium text-ink-gray-8">Visibility</p>
              <Select
                class="mt-2 w-full"
                :model-value="page.visible ? 'visible' : 'hidden'"
                :options="[{ value: 'visible', label: 'Visible' }, { value: 'hidden', label: 'Hidden' }]"
                @update:model-value="(value) => (page.visible = value === 'visible')"
              />
            </div>
            <div class="rounded-lg border border-outline-gray-2 p-4" data-theme-template>
              <p class="text-sm font-medium text-ink-gray-8">Theme template</p>
              <Select v-model="page.template" class="mt-2 w-full" :options="templatesFor(theme)" />
              <p class="mt-2 text-sm text-ink-gray-5">
                From <span class="font-medium text-ink-gray-7">{{ theme.title }}</span>, your live theme. It adds the header, footer and layout around your text.
              </p>
            </div>
            <div class="space-y-2 rounded-lg border border-outline-gray-2 p-4">
              <p class="text-sm font-medium text-ink-gray-8">Search engine listing</p>
              <TextInput :model-value="page.title" placeholder="Page title" />
              <Textarea :rows="2" placeholder="Meta description" />
              <TextInput :model-value="page.name" placeholder="url-handle" />
              <p class="text-xs text-ink-gray-5">yourstore.com/en/{{ page.name }}</p>
            </div>
            <Badge :label="page.visible ? 'Visible on your store' : 'Hidden from your store'" :theme="page.visible ? 'green' : 'gray'" />
          </div>
        </div>
      </div>
    </template>
  </StorefrontShell>
</template>
