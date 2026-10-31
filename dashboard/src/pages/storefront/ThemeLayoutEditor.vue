<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { useEventListener, useMediaQuery } from '@vueuse/core'
import { Badge, Button, Dropdown, Skeleton, TabButtons, dialog, toast } from 'frappe-ui'
import EmptyState from '../../components/EmptyState.vue'
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
  if (await editor.publish()) toast.success('Published to your store')
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
          <Badge v-else label="Live" theme="green" variant="subtle" />
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

      <div class="flex min-h-0 flex-1">
        <aside
          v-show="isWide || panel === 'tree'"
          class="w-full min-w-0 shrink-0 overflow-y-auto p-2 lg:w-72 lg:border-r lg:border-outline-gray-2"
        >
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
        </aside>

        <main v-show="isWide || panel === 'preview'" class="min-w-0 flex-1">
          <LayoutPreviewFrame :editor="editor" />
        </main>

        <aside
          v-show="isWide || panel === 'settings'"
          class="w-full min-w-0 shrink-0 lg:w-80 lg:border-l lg:border-outline-gray-2"
        >
          <LayoutSettingsPanel v-if="state.loaded" :editor="editor" />
        </aside>
      </div>
    </template>
  </div>
</template>
