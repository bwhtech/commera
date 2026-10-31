<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { createReusableTemplate, useEventListener, useMediaQuery } from '@vueuse/core'
import { SplitterGroup, SplitterPanel, SplitterResizeHandle } from 'reka-ui'
import { Badge, Button, Dropdown, Skeleton, TabButtons, Tooltip, dialog, toast } from 'frappe-ui'
import EmptyState from '../../components/EmptyState.vue'
import LayoutPreviewCanvas from '../../components/storefront/LayoutPreviewCanvas.vue'
import LayoutPreviewFrame from '../../components/storefront/LayoutPreviewFrame.vue'
import LayoutSectionPicker from '../../components/storefront/LayoutSectionPicker.vue'
import LayoutSectionTree from '../../components/storefront/LayoutSectionTree.vue'
import LayoutSettingsPanel from '../../components/storefront/LayoutSettingsPanel.vue'
import { SECTION_GROUPS, createLayoutEditor, pageLabel } from '../../data/themeLayout'
import { errorMessage } from '../../data/errors'

const LANGUAGES = [
  { label: 'EN', value: 'en' },
  { label: 'AR', value: 'ar' },
]

const DEVICES = [
  { label: 'Desktop', value: 'desktop', icon: 'lucide-monitor' },
  { label: 'Mobile', value: 'mobile', icon: 'lucide-smartphone' },
  { label: 'Desktop and mobile', value: 'both', icon: 'lucide-columns-2' },
]

const PANELS = [
  { label: 'Sections', value: 'tree' },
  { label: 'Preview', value: 'preview' },
  { label: 'Settings', value: 'settings' },
]

const route = useRoute()
const router = useRouter()

const editor = createLayoutEditor(String(route.params.theme))
const { state, hasUnsavedChanges, hasUnpublishedChanges, busy, saveIfChanged, switchPage } = editor

const pickingGroup = ref(null)

const isWide = useMediaQuery('(min-width: 1024px)')
const panel = ref('tree')

const [DefineTreePanel, TreePanel] = createReusableTemplate()

const treePanel = ref(null)
const settingsPanel = ref(null)
const treeOpen = ref(true)
const settingsOpen = ref(true)
const maximised = ref(null)

const railItems = computed(() => [
  { label: 'Sections', icon: 'lucide-list-tree', active: treeOpen.value, onClick: toggleTree },
  {
    label: 'Section settings',
    icon: 'lucide-sliders-horizontal',
    active: settingsOpen.value && state.selection?.kind !== 'theme',
    onClick: () => toggleSettings(false),
  },
  {
    label: 'Theme settings',
    icon: 'lucide-palette',
    active: settingsOpen.value && state.selection?.kind === 'theme',
    onClick: () => toggleSettings(true),
  },
])

function toggleTree() {
  if (treeOpen.value) treePanel.value.collapse()
  else treePanel.value.expand()
}

function toggleSettings(theme) {
  const showingTheme = state.selection?.kind === 'theme'
  if (settingsOpen.value && showingTheme === theme) {
    settingsPanel.value.collapse()
    return
  }
  if (theme) editor.select({ kind: 'theme' }, { scroll: false })
  else if (showingTheme) editor.select(null)
  settingsPanel.value.expand()
}

const PANEL_OPEN = { tree: treeOpen, settings: settingsOpen }

function panelExpanded(name) {
  PANEL_OPEN[name].value = true
  maximised.value = null
}

function toggleMaximise() {
  const previous = maximised.value
  if (previous) {
    maximised.value = null
    if (previous.tree) treePanel.value.expand()
    if (previous.settings) settingsPanel.value.expand()
    return
  }
  maximised.value = { tree: treeOpen.value, settings: settingsOpen.value }
  treePanel.value.collapse()
  settingsPanel.value.collapse()
}

watch([treePanel, settingsPanel], () => {
  if (treePanel.value) treeOpen.value = !treePanel.value.isCollapsed
  if (settingsPanel.value) settingsOpen.value = !settingsPanel.value.isCollapsed
})

watch(
  () => state.selection,
  (selection) => {
    if (selection && !isWide.value) panel.value = 'settings'
  },
)

onMounted(() => editor.load())

const pageOptions = computed(() =>
  state.pages
    .filter((page) => !SECTION_GROUPS.includes(page))
    .map((page) => ({
      label: pageLabel(page),
      icon: page === state.page ? 'lucide-check' : 'lucide-file',
      onClick: () => switchPage(page),
    })),
)

function pickSection(type) {
  editor.addSection(pickingGroup.value, type)
  pickingGroup.value = null
}

async function save() {
  if (await editor.save()) toast.success('Draft saved')
}

async function publish() {
  if (!(await editor.publish())) return
  toast.success(state.live ? 'Published to your store' : `Published. Activate ${state.theme} to show it in your store.`)
}

function discard() {
  dialog.confirm({
    title: 'Discard unpublished changes?',
    message: 'The layout goes back to what your store shows now.',
    theme: 'red',
    confirmLabel: 'Discard',
    onConfirm: async () => {
      if (await editor.discard()) toast.success('Changes discarded')
    },
  })
}

onBeforeRouteLeave(async () => (state.loadError ? true : await saveIfChanged()))

useEventListener(window, 'beforeunload', (event) => {
  if (hasUnsavedChanges.value) event.preventDefault()
})
</script>

<template>
  <div class="flex h-screen flex-col bg-surface-base" data-theme-layout-editor>
    <header class="flex shrink-0 flex-wrap items-center gap-2 border-b border-outline-gray-2 px-3 py-2">
      <Button
        variant="ghost"
        icon-left="lucide-arrow-left"
        label="Themes"
        @click="router.push({ name: 'StorefrontTheme' })"
      />
      <div class="flex min-w-0 items-center gap-2">
        <span class="truncate text-base font-medium text-ink-gray-9">{{ state.theme }}</span>
        <template v-if="state.loaded && !state.loadError">
          <Badge v-if="hasUnpublishedChanges" label="Unpublished changes" theme="orange" variant="subtle" />
          <Badge v-else-if="state.live" label="Live" theme="green" variant="subtle" />
          <Badge v-else label="Not live" theme="gray" variant="subtle" />
        </template>
      </div>

      <div class="order-last flex w-full flex-wrap items-center gap-2 lg:order-none lg:mx-auto lg:w-auto">
        <Dropdown :options="pageOptions">
          <Button icon-left="lucide-file" icon-right="lucide-chevron-down" :label="pageLabel(state.page)" />
        </Dropdown>
        <TabButtons v-model="state.language" :options="LANGUAGES" aria-label="Language" />
        <TabButtons v-if="isWide" v-model="state.device" :options="DEVICES" aria-label="Preview width" />
      </div>

      <div class="ms-auto flex items-center gap-2 lg:ms-0">
        <Button variant="ghost" label="Discard" :disabled="!hasUnpublishedChanges || busy" @click="discard" />
        <Button label="Save" :disabled="!hasUnsavedChanges" :loading="busy" @click="save" />
        <Button
          variant="solid"
          label="Publish"
          :disabled="!hasUnpublishedChanges && !hasUnsavedChanges"
          :loading="busy"
          @click="publish"
        />
      </div>
    </header>

    <EmptyState
      v-if="state.loadError"
      class="mt-16"
      icon="lucide-triangle-alert"
      title="Could not open this theme"
      :description="errorMessage(state.loadError)"
    />

    <template v-else>
      <div v-if="!isWide" class="shrink-0 border-b border-outline-gray-2 px-3 py-2">
        <TabButtons v-model="panel" class="w-full" :options="PANELS" aria-label="Panel" />
      </div>

      <DefineTreePanel>
        <div v-if="!state.loaded" class="flex flex-col gap-2 p-2" aria-hidden="true">
          <Skeleton v-for="row in 8" :key="row" class="h-6 w-full rounded-4" />
        </div>
        <LayoutSectionPicker
          v-else-if="pickingGroup"
          :schemas="state.schemas"
          :group="pickingGroup"
          @pick="pickSection"
          @back="pickingGroup = null"
        />
        <LayoutSectionTree v-else :editor="editor" @add-section="pickingGroup = $event" />
      </DefineTreePanel>

      <div v-if="isWide" class="flex min-h-0 flex-1">
        <nav class="flex w-11 shrink-0 flex-col items-center gap-1 border-r border-outline-gray-2 py-2" aria-label="Panels">
          <Tooltip v-for="item in railItems" :key="item.label" :text="item.label" placement="right">
            <Button
              :variant="item.active ? 'subtle' : 'ghost'"
              :icon="item.icon"
              :aria-label="item.label"
              :aria-pressed="item.active"
              @click="item.onClick"
            />
          </Tooltip>
        </nav>

        <SplitterGroup direction="horizontal" auto-save-id="commera-theme-editor-panels" class="min-w-0 flex-1">
          <SplitterPanel
            id="theme-editor-tree"
            ref="treePanel"
            :order="1"
            size-unit="px"
            :default-size="288"
            :min-size="220"
            :max-size="440"
            collapsible
            :collapsed-size="0"
            class="!overflow-y-auto"
            data-editor-panel="tree"
            @collapse="treeOpen = false"
            @expand="panelExpanded('tree')"
          >
            <div class="p-2">
              <TreePanel />
            </div>
          </SplitterPanel>
          <SplitterResizeHandle
            class="relative z-10 w-0 border-l border-outline-gray-2 transition-colors after:absolute after:inset-y-0 after:-left-1 after:-right-1 after:content-[''] data-[state=drag]:border-outline-gray-4 data-[state=hover]:border-outline-gray-4"
            data-editor-handle="tree"
          />
          <SplitterPanel id="theme-editor-preview" :order="2" class="min-w-0">
            <LayoutPreviewCanvas :editor="editor" :maximised="Boolean(maximised)" @toggle-maximise="toggleMaximise" />
          </SplitterPanel>
          <SplitterResizeHandle
            class="relative z-10 w-0 border-l border-outline-gray-2 transition-colors after:absolute after:inset-y-0 after:-left-1 after:-right-1 after:content-[''] data-[state=drag]:border-outline-gray-4 data-[state=hover]:border-outline-gray-4"
            data-editor-handle="settings"
          />
          <SplitterPanel
            id="theme-editor-settings"
            ref="settingsPanel"
            :order="3"
            size-unit="px"
            :default-size="320"
            :min-size="260"
            :max-size="480"
            collapsible
            :collapsed-size="0"
            data-editor-panel="settings"
            @collapse="settingsOpen = false"
            @expand="panelExpanded('settings')"
          >
            <LayoutSettingsPanel v-if="state.loaded" :editor="editor" />
          </SplitterPanel>
        </SplitterGroup>
      </div>

      <div v-else class="flex min-h-0 flex-1">
        <aside v-show="panel === 'tree'" class="w-full min-w-0 overflow-y-auto p-2">
          <TreePanel />
        </aside>

        <main v-show="panel === 'preview'" class="min-w-0 flex-1 bg-surface-gray-2 p-4">
          <div class="h-full overflow-hidden rounded-5 border border-outline-gray-2 bg-surface-base shadow-sm">
            <LayoutPreviewFrame :editor="editor" />
          </div>
        </main>

        <aside v-show="panel === 'settings'" class="w-full min-w-0">
          <LayoutSettingsPanel v-if="state.loaded" :editor="editor" />
        </aside>
      </div>
    </template>
  </div>
</template>
