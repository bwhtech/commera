<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { createReusableTemplate, useEventListener, useLocalStorage, useMediaQuery } from '@vueuse/core'
import { SplitterGroup, SplitterPanel, SplitterResizeHandle } from 'reka-ui'
import { Badge, Breadcrumbs, Button, Dropdown, Skeleton, TabButtons, Tooltip, dialog, toast } from 'frappe-ui'
import EmptyState from '../../components/EmptyState.vue'
import LayoutPreviewCanvas from '../../components/storefront/LayoutPreviewCanvas.vue'
import LayoutPreviewFrame from '../../components/storefront/LayoutPreviewFrame.vue'
import LayoutSectionPicker from '../../components/storefront/LayoutSectionPicker.vue'
import LayoutSectionTree from '../../components/storefront/LayoutSectionTree.vue'
import LayoutSettingsPanel from '../../components/storefront/LayoutSettingsPanel.vue'
import PreviewEntryPicker from '../../components/storefront/PreviewEntryPicker.vue'
import ThemeSettingsPanel from '../../components/storefront/ThemeSettingsPanel.vue'
import PreviewOptions from '../../components/storefront/PreviewOptions.vue'
import { SECTION_GROUPS, createLayoutEditor, pageLabel } from '../../data/themeLayout'
import { errorMessage } from '../../data/errors'

const PANELS = [
  { label: 'Sections', value: 'tree' },
  { label: 'Preview', value: 'preview' },
  { label: 'Settings', value: 'settings' },
]

const route = useRoute()

const editor = createLayoutEditor(String(route.params.theme))
const { state, hasUnsavedChanges, hasUnpublishedChanges, busy, saveIfChanged, switchPage } = editor

const pickingGroup = ref(null)

const isWide = useMediaQuery('(min-width: 1024px)')
const panel = ref('tree')

const [DefineTreePanel, TreePanel] = createReusableTemplate()

const treePanel = ref(null)
const treeWidth = useLocalStorage('commera-theme-editor-panels', 288)
const settingsOpen = ref(true)
const maximised = ref(null)
const pendingAction = ref(null)

const themeSettingsOpen = ref(false)
const themeSettingsDirty = ref(false)
const themeSettingsMounted = ref(false)
let selectionBeforeThemeSettings = null

const hasSettings = computed(() => Boolean(state.selection) || themeSettingsOpen.value)
const panels = computed(() => PANELS.filter((option) => option.value !== 'settings' || hasSettings.value))

watch(themeSettingsOpen, (open) => {
  if (!open) themeSettingsMounted.value = false
})

watch(hasSettings, (shown) => {
  if (!shown && panel.value === 'settings') panel.value = 'tree'
})


function showSettingsSlot() {
  if (!isWide.value) panel.value = 'settings'
  else if (!maximised.value) settingsOpen.value = true
}

function closeThemeSettings(then) {
  themeSettingsOpen.value = false
  if (then) then()
  else if (selectionBeforeThemeSettings) editor.select(selectionBeforeThemeSettings, { scroll: false })
  selectionBeforeThemeSettings = null
}

function leaveThemeSettings(then) {
  if (!themeSettingsDirty.value) return closeThemeSettings(then)
  dialog.confirm({
    title: 'Discard unsaved theme settings?',
    message: 'The changes you have not saved are lost.',
    theme: 'red',
    confirmLabel: 'Discard',
    onConfirm: () => {
      themeSettingsDirty.value = false
      closeThemeSettings(then)
    },
  })
}

async function toggleThemeSettings() {
  if (themeSettingsOpen.value) return leaveThemeSettings()
  selectionBeforeThemeSettings = state.selection
  editor.select(null)
  if (!isWide.value) panel.value = 'settings'
  else {
    themeSettingsMounted.value = true
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  }
  themeSettingsOpen.value = true
}

const breadcrumbs = computed(() => [
  { label: 'Themes', route: { name: 'StorefrontTheme' } },
  { label: state.theme },
])

async function toggleMaximise() {
  const previous = maximised.value
  if (previous) {
    treePanel.value.expand()
    await nextTick()
    maximised.value = null
    settingsOpen.value = previous.settings
    await nextTick()
    treePanel.value.resize(previous.treeSize)
    return
  }
  maximised.value = { settings: settingsOpen.value, treeSize: treePanel.value.getSize() }
  await nextTick()
  treePanel.value.collapse()
  settingsOpen.value = false
}

watch(
  () => state.selection,
  (selection) => {
    if (!selection) return
    if (themeSettingsOpen.value && themeSettingsDirty.value) {
      editor.select(null)
      leaveThemeSettings(() => editor.select(selection))
      return
    }
    themeSettingsOpen.value = false
    showSettingsSlot()
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

async function track(label, work) {
  pendingAction.value = label
  try {
    return await work()
  } finally {
    pendingAction.value = null
  }
}

async function save() {
  if (await track('Save', () => editor.save())) toast.success('Draft saved')
}

async function publish() {
  if (!(await track('Publish', () => editor.publish()))) return
  toast.success(state.live ? 'Published to your store' : `Published. Activate ${state.theme} to show it in your store.`)
}

function discard() {
  dialog.confirm({
    title: 'Discard all unpublished changes?',
    message: 'The layout goes back to what your store shows now.',
    theme: 'red',
    confirmLabel: 'Discard',
    onConfirm: async () => {
      if (await track('Discard', () => editor.discard())) toast.success('Changes discarded')
    },
  })
}

const actions = computed(() => [
  {
    label: 'Discard',
    variant: 'subtle',
    reason: hasUnpublishedChanges.value ? null : 'Nothing to discard',
    onClick: discard,
  },
  {
    label: 'Save',
    variant: 'solid',
    reason: hasUnsavedChanges.value ? null : 'No unsaved changes',
    onClick: save,
  },
  {
    label: 'Publish',
    variant: 'solid',
    reason: hasUnsavedChanges.value
      ? 'Save your changes first'
      : hasUnpublishedChanges.value
        ? null
        : 'Everything is already live',
    onClick: publish,
  },
])

onBeforeRouteLeave(async () => (state.loadError ? true : await saveIfChanged()))

useEventListener(window, 'beforeunload', (event) => {
  if (hasUnsavedChanges.value) event.preventDefault()
})
</script>

<template>
  <div class="relative flex h-screen flex-col bg-surface-base" data-theme-layout-editor>
    <header
      class="flex shrink-0 flex-wrap items-center gap-2 border-b border-outline-gray-2 px-3 py-2"
      :class="{ 'me-80 transition-[margin] duration-200 motion-reduce:transition-none': themeSettingsOpen && isWide }"
    >
      <div class="flex min-w-0 items-center gap-2">
        <Breadcrumbs class="min-w-0" :items="breadcrumbs" />
        <template v-if="state.loaded && !state.loadError">
          <Badge v-if="hasUnpublishedChanges" label="Unpublished changes" theme="orange" variant="subtle" />
          <Badge v-else label="Published" theme="green" variant="subtle" />
          <Badge v-if="!state.live" label="Not live" theme="gray" variant="subtle" />
        </template>
      </div>

      <div class="order-last flex w-full flex-wrap items-center gap-2 lg:order-none lg:mx-auto lg:w-auto">
        <Dropdown :options="pageOptions">
          <Button icon-left="lucide-file" icon-right="lucide-chevron-down" :label="pageLabel(state.page)" />
        </Dropdown>
        <PreviewEntryPicker v-if="state.loaded && state.hasPreviewEntries" :editor="editor" />
      </div>

      <div class="ms-auto flex items-center gap-2 lg:ms-0">
        <Tooltip v-for="action in actions" :key="action.label" :text="action.reason" :disabled="!action.reason">
          <span class="inline-flex" :tabindex="action.reason ? 0 : undefined">
            <Button
              :variant="action.variant"
              :label="action.label"
              :class="{ 'pointer-events-none': action.reason }"
              :disabled="Boolean(action.reason) || (busy && pendingAction !== action.label)"
              :loading="pendingAction === action.label"
              @click="action.onClick"
            />
          </span>
        </Tooltip>
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
      <div v-if="!isWide" class="flex shrink-0 items-center gap-2 border-b border-outline-gray-2 px-3 py-2">
        <TabButtons v-model="panel" class="min-w-0 flex-1" :options="panels" aria-label="Panel" />
        <PreviewOptions :state="state" :devices="false" />
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
        <SplitterGroup direction="horizontal" class="min-w-0 flex-1">
          <SplitterPanel
            id="theme-editor-tree"
            ref="treePanel"
            :order="1"
            size-unit="px"
            :default-size="treeWidth"
            :min-size="220"
            :max-size="440"
            :collapsible="Boolean(maximised)"
            :collapsed-size="0"
            class="flex flex-col"
            data-editor-panel="tree"
            @resize="treePanel && !maximised && (treeWidth = Math.round(treePanel.getSize()))"
          >
            <div class="min-h-0 flex-1 overflow-y-auto p-2">
              <TreePanel />
            </div>
            <div class="shrink-0 border-t border-outline-gray-2 p-2">
              <Button
                class="w-full !justify-start"
                :variant="themeSettingsOpen ? 'subtle' : 'ghost'"
                icon-left="lucide-settings"
                label="Theme settings"
                :aria-pressed="themeSettingsOpen"
                data-theme-settings-toggle
                @click="toggleThemeSettings"
              />
            </div>
          </SplitterPanel>
          <SplitterResizeHandle
            class="relative z-10 w-0 border-l border-outline-gray-2 transition-colors after:absolute after:inset-y-0 after:-left-1 after:-right-1 after:content-[''] data-[state=drag]:border-outline-gray-4 data-[state=hover]:border-outline-gray-4"
            data-editor-handle="tree"
          />
          <SplitterPanel id="theme-editor-preview" :order="2" class="min-w-0">
            <LayoutPreviewCanvas :editor="editor" :maximised="Boolean(maximised)" @toggle-maximise="toggleMaximise" />
          </SplitterPanel>
        </SplitterGroup>
        <aside
          v-show="settingsOpen && hasSettings"
          id="theme-editor-settings"
          class="w-80 shrink-0 border-s border-outline-gray-2"
          data-editor-panel="settings"
        >
          <LayoutSettingsPanel v-if="state.loaded && state.selection" :editor="editor" />
        </aside>
      </div>

      <div v-else class="flex min-h-0 flex-1">
        <aside v-show="panel === 'tree'" class="flex w-full min-w-0 flex-col">
          <div class="min-h-0 flex-1 overflow-y-auto p-2">
            <TreePanel />
          </div>
          <div class="shrink-0 border-t border-outline-gray-2 p-2">
            <Button
              class="w-full !justify-start"
              variant="ghost"
              icon-left="lucide-settings"
              label="Theme settings"
              data-theme-settings-toggle
              @click="toggleThemeSettings"
            />
          </div>
        </aside>

        <main v-show="panel === 'preview'" class="min-w-0 flex-1 bg-surface-gray-2 p-4">
          <div class="h-full overflow-hidden rounded-5 border border-outline-gray-2 bg-surface-base shadow-sm">
            <LayoutPreviewFrame :editor="editor" />
          </div>
        </main>

        <aside v-show="panel === 'settings'" class="w-full min-w-0">
          <template v-if="state.loaded">
            <ThemeSettingsPanel
              v-if="themeSettingsOpen"
              :editor="editor"
              @close="leaveThemeSettings()"
              @dirty="themeSettingsDirty = $event"
            />
            <LayoutSettingsPanel v-else :editor="editor" />
          </template>
        </aside>
      </div>
    </template>

    <aside
      v-if="isWide && state.loaded && themeSettingsMounted"
      class="absolute inset-y-0 end-0 z-20 overflow-hidden border-s border-outline-gray-2 bg-surface-base transition-[width] duration-200 motion-reduce:transition-none"
      :class="themeSettingsOpen ? 'w-80' : 'w-0'"
    >
      <ThemeSettingsPanel
        class="absolute inset-y-0 end-0 w-80"
        :editor="editor"
        @close="leaveThemeSettings()"
        @dirty="themeSettingsDirty = $event"
      />
    </aside>
  </div>
</template>
