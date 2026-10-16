<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Dropdown, TabButtons, dialog, toast } from 'frappe-ui'
import { TEMPLATES } from '../theme/schemas.js'
import { createEditor } from '../editor/state.js'
import SectionTree from '../editor/SectionTree.vue'
import SettingsPanel from '../editor/SettingsPanel.vue'
import PreviewFrame from '../editor/PreviewFrame.vue'
import LayoutJsonDialog from '../editor/LayoutJsonDialog.vue'
import NewPageDialog from '../editor/NewPageDialog.vue'
import { BUILDER_PAGES, builderUrl } from '../theme/builder.js'
import { openBuilder } from '../editor/openBuilder.js'

const route = useRoute()
const router = useRouter()
const editor = createEditor(route.params.theme)
// Opened from Pages with ?page=: start on that page (theme template or builder:<name>).
if (route.query.page) editor.state.template = String(route.query.page)
const { state, builderPage, hasUnsavedChanges, hasUnpublishedChanges, saveDraft, publish, discardDraft } = editor

const themeTitle = computed(() => ({ summer_theme: 'Summer', shop_default_theme: 'Shop Default', atelier_theme: 'Atelier' })[state.theme] ?? state.theme)
const showJson = ref(false)
const showNewPage = ref(false)

// One picker for every storefront page: theme pages are edited here section by
// section; Builder pages are listed so merchants find all pages in one place,
// and open in Builder for their content.
const pageLabel = computed(() =>
  builderPage.value ? builderPage.value.title : TEMPLATES.find(({ value }) => value === state.template)?.label,
)
const pageOptions = computed(() => [
  {
    group: 'Theme pages',
    options: TEMPLATES.map((template) => ({ label: template.label, icon: template.icon, onClick: () => (state.template = template.value) })),
  },
  {
    group: 'Built in Frappe Builder',
    options: BUILDER_PAGES.map((page) => ({
      label: page.title,
      icon: 'lucide-blocks',
      onClick: () => (state.template = `builder:${page.name}`),
    })),
  },
  { group: 'New', hideLabel: true, options: [{ label: 'New page…', icon: 'lucide-plus', onClick: () => (showNewPage.value = true) }] },
])

function onPageCreated(page) {
  state.template = `builder:${page.name}`
}

// Rearranging a live homepage is not a field that "settles": it goes live only
// on Publish. Save keeps a draft; this is the one place the dashboard's
// save-per-field rule deliberately does not apply.
function onPublish() {
  publish()
  toast.success('Published to your storefront')
}

function onSave() {
  saveDraft()
  toast.success('Draft saved')
}

function onDiscard() {
  dialog.confirm({
    title: 'Discard unpublished changes?',
    message: 'The editor goes back to what your storefront shows now.',
    confirmLabel: 'Discard',
    theme: 'red',
    onConfirm: discardDraft,
  })
}

function leave() {
  if (hasUnsavedChanges.value) saveDraft()
  router.push('/')
}
</script>

<template>
  <div class="flex h-screen flex-col" data-theme-editor>
    <header class="flex h-12 shrink-0 items-center gap-3 border-b border-outline-gray-2 px-3">
      <Button variant="ghost" icon="lucide-arrow-left" label="Back to themes" @click="leave" />
      <div class="flex min-w-0 items-center gap-2">
        <span class="truncate text-base font-semibold text-ink-gray-9">{{ themeTitle }}</span>
        <Badge v-if="hasUnpublishedChanges" label="Unpublished changes" theme="orange" />
        <Badge v-else label="Live" theme="green" />
      </div>

      <div class="mx-auto flex items-center gap-2">
        <Dropdown :options="pageOptions">
          <Button
            class="w-52 justify-between"
            :icon-left="builderPage ? 'lucide-blocks' : 'lucide-file'"
            icon-right="lucide-chevron-down"
            :label="pageLabel"
            data-page-picker
          />
        </Dropdown>
        <TabButtons
          v-model="state.language"
          :options="[{ value: 'en', label: 'EN' }, { value: 'ar', label: 'AR' }]"
        />
        <TabButtons
          v-model="state.device"
          :options="[
            { value: 'desktop', icon: 'lucide-monitor', label: 'Desktop' },
            { value: 'mobile', icon: 'lucide-smartphone', label: 'Mobile' },
          ]"
        />
      </div>

      <Button variant="ghost" icon="lucide-braces" label="View layout data" @click="showJson = true" />
      <Dropdown :options="[{ label: 'Discard unpublished changes', icon: 'lucide-undo-2', theme: 'red', onClick: onDiscard }]">
        <Button variant="ghost" icon="lucide-ellipsis" label="More" />
      </Dropdown>
      <Button label="Save" :disabled="!hasUnsavedChanges" @click="onSave" />
      <Button variant="solid" label="Publish" :disabled="!hasUnpublishedChanges" @click="onPublish" />
    </header>

    <div class="flex min-h-0 flex-1">
      <!-- min-w-0 on the flex children: without it the tree's longest label sets
           the column's minimum width and pushes the preview off-screen. -->
      <aside class="w-80 min-w-0 shrink-0 overflow-y-auto border-r border-outline-gray-2 p-2" data-tree-panel>
        <div v-if="builderPage" class="mb-2 rounded border border-outline-gray-2 bg-surface-gray-1 p-3" data-builder-page-card>
          <p class="text-base font-medium text-ink-gray-9">{{ builderPage.title }} is built in Frappe Builder</p>
          <p class="mt-1 text-sm text-ink-gray-6">
            {{
              builderPage.layout === 'commera-theme'
                ? 'Its content is edited in Builder. The header and footer below come from this theme.'
                : 'Its content and chrome are edited in Builder; it does not use the store header and footer.'
            }}
          </p>
          <Button
            class="mt-2"
            size="sm"
            icon-left="lucide-pencil"
            label="Edit in Builder"
            @click="openBuilder(builderUrl('page', { name: builderPage.name }), builderPage.title)"
          />
        </div>
        <SectionTree :editor="editor" />
      </aside>
      <main class="min-w-0 flex-1">
        <PreviewFrame :editor="editor" />
      </main>
      <aside class="w-80 min-w-0 shrink-0 border-l border-outline-gray-2">
        <SettingsPanel :editor="editor" />
      </aside>
    </div>

    <LayoutJsonDialog v-model:open="showJson" :editor="editor" />
    <NewPageDialog v-model:open="showNewPage" @created="onPageCreated" />
  </div>
</template>
