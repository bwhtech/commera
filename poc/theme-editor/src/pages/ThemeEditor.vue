<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Dropdown, Select, TabButtons, dialog, toast } from 'frappe-ui'
import { TEMPLATES } from '../theme/schemas.js'
import { createEditor } from '../editor/state.js'
import SectionTree from '../editor/SectionTree.vue'
import SettingsPanel from '../editor/SettingsPanel.vue'
import PreviewFrame from '../editor/PreviewFrame.vue'
import LayoutJsonDialog from '../editor/LayoutJsonDialog.vue'

const route = useRoute()
const router = useRouter()
const editor = createEditor(route.params.theme)
const { state, hasUnsavedChanges, hasUnpublishedChanges, saveDraft, publish, discardDraft } = editor

const themeTitle = computed(() => ({ summer_theme: 'Summer', shop_default_theme: 'Shop Default', atelier_theme: 'Atelier' })[state.theme] ?? state.theme)
const showJson = ref(false)

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
        <Select v-model="state.template" class="w-44" :options="TEMPLATES.map(({ value, label }) => ({ value, label }))" data-template-select />
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
  </div>
</template>
