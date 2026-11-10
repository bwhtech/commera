<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useEventListener, useWindowSize } from '@vueuse/core'
import { Button, TabButtons } from 'frappe-ui'
import { storefrontLanguageOptions } from '../../data/boot'

const props = defineProps({
  // Bumped by every mutation; it is what makes the iframe refetch the rendered chrome.
  token: { type: Number, required: true },
  path: { type: String, required: true },
  title: { type: String, required: true },
  selector: { type: String, required: true },
  // Extra query params the previewed page reads, e.g. which theme to render.
  params: { type: Object, default: () => ({}) },
})

const collapsed = defineModel('collapsed', { type: Boolean, required: true })

const FRAME_WIDTH = 1440
const FALLBACK_FRAME_HEIGHT = 560
const MIN_STAGE_HEIGHT = 160
const RESIZE_STEP = 40
// A hovered mega-menu opens under the navbar, so a frame ending at the chrome bottom
// clips it out of existence.
const DROPDOWN_HEADROOM = 460

const language = ref(storefrontLanguageOptions[0]?.value ?? 'en')
const reloadToken = ref(0)
const contentHeight = ref(0)

const stage = ref(null)
const stageWidth = ref(0)
let stageObserver = null
// Watches the previewed document itself: webfonts and images land after `load`, and the
// footer settles taller (or shorter) than it measured at first paint.
let frameObserver = null

const { height: windowHeight } = useWindowSize()

onMounted(() => {
  stageObserver = new ResizeObserver(([entry]) => {
    stageWidth.value = entry.contentRect.width
  })
  if (stage.value) stageObserver.observe(stage.value)
})

onBeforeUnmount(() => {
  stageObserver?.disconnect()
  frameObserver?.disconnect()
})

// No `min(1, …)` cap: past 1440px the frame would sit at its natural width and leave a dead
// strip beside it, so the preview is stretched to whatever width the pane actually has.
const scale = computed(() => (stageWidth.value ? stageWidth.value / FRAME_WIDTH : 1))

const headroom = computed(() => (props.selector === 'header' ? DROPDOWN_HEADROOM : 0))

// Sizing the frame to the pane crops the footer-bottom strip, so it is driven by the
// rendered chrome instead.
const frameHeight = computed(() => (contentHeight.value || FALLBACK_FRAME_HEIGHT) + headroom.value)

// The editor board above must survive the drag, so the pane can never own the whole viewport.
const maxStageHeight = computed(() =>
  Math.max(MIN_STAGE_HEIGHT, Math.round(windowHeight.value * 0.7)),
)

function clampHeight(height) {
  return Math.min(Math.max(Math.round(height), MIN_STAGE_HEIGHT), maxStageHeight.value)
}

const storageKey = `commera-preview-height:${props.path}`

function readStoredHeight() {
  try {
    return Number(window.localStorage.getItem(storageKey)) || 0
  } catch {
    // Private-mode storage throws on read; the pane just falls back to fitting its content.
    return 0
  }
}

// Zero means untouched: the pane keeps fitting itself to the rendered chrome until the user drags it.
const userHeight = ref(readStoredHeight())

const stageHeight = computed(() =>
  clampHeight(userHeight.value || frameHeight.value * scale.value),
)

const resizing = ref(false)
let resizeOrigin = 0
let resizeBaseHeight = 0

function resizeTo(height) {
  userHeight.value = clampHeight(height)
  try {
    window.localStorage.setItem(storageKey, String(userHeight.value))
  } catch {
    // Remembering the height across reloads is a convenience, never a reason to break the pane.
  }
}

function startResize(event) {
  if (collapsed.value) return
  resizing.value = true
  resizeOrigin = event.clientY
  resizeBaseHeight = stageHeight.value
  // Without capture the preview iframe swallows every pointermove the moment the cursor crosses into it.
  event.currentTarget.setPointerCapture(event.pointerId)
}

useEventListener(window, 'pointermove', (event) => {
  if (!resizing.value) return
  event.preventDefault()
  // The pane is anchored at the bottom of the editor, so it grows towards the cursor: up is taller.
  resizeTo(resizeBaseHeight + (resizeOrigin - event.clientY))
})

useEventListener(window, 'pointerup', () => {
  resizing.value = false
})

function measureChrome(previewDocument) {
  // Measured off the chrome itself: a full-height themed page's scrollHeight would hang
  // an empty storefront under the navbar.
  const chrome = previewDocument?.querySelector(props.selector)
  contentHeight.value = chrome
    ? Math.ceil(chrome.getBoundingClientRect().bottom)
    : (previewDocument?.documentElement?.scrollHeight ?? 0)
}

function measureFrame(event) {
  frameObserver?.disconnect()
  try {
    const previewDocument = event.target.contentDocument
    measureChrome(previewDocument)
    if (!previewDocument?.body) return
    frameObserver = new ResizeObserver(() => measureChrome(previewDocument))
    frameObserver.observe(previewDocument.body)
  } catch {
    // Same-origin today, but a cross-origin redirect must leave the pane on its fallback height.
    contentHeight.value = 0
  }
}

const source = computed(() => {
  const query = new URLSearchParams({
    ...props.params,
    lang: language.value,
    t: `${props.token}-${reloadToken.value}`,
  })
  return `${props.path}?${query}`
})
</script>

<template>
  <div
    class="relative mt-4 rounded-6 border border-outline-gray-1 bg-surface-gray-1"
    :class="resizing && 'select-none'"
  >
    <div
      v-if="!collapsed"
      role="separator"
      aria-orientation="horizontal"
      tabindex="0"
      :aria-label="`Resize ${title.toLowerCase()}`"
      class="group absolute inset-x-0 top-0 z-10 flex h-2 -translate-y-1/2 cursor-ns-resize touch-none items-center justify-center focus:outline-none"
      @pointerdown="startResize"
      @keydown.up.prevent="resizeTo(stageHeight + RESIZE_STEP)"
      @keydown.down.prevent="resizeTo(stageHeight - RESIZE_STEP)"
    >
      <div
        class="h-1 w-10 rounded-full bg-surface-gray-3 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
        :class="resizing && 'opacity-100'"
      />
    </div>

    <div class="flex min-h-11 items-center justify-between gap-2 px-3">
      <div class="flex items-center gap-2">
        <Button
          variant="ghost"
          :icon-left="collapsed ? 'lucide-chevron-up' : 'lucide-chevron-down'"
          :label="collapsed ? `Show ${title.toLowerCase()}` : title"
          @click="collapsed = !collapsed"
        />
        <TabButtons
          v-if="!collapsed && storefrontLanguageOptions.length > 1"
          v-model="language"
          size="sm"
          :options="storefrontLanguageOptions"
        />
      </div>

      <Button v-if="!collapsed" icon-left="lucide-rotate-cw" label="Refresh" @click="reloadToken += 1" />
    </div>

    <div v-if="!collapsed" class="px-3 pb-3">
      <div
        ref="stage"
        class="overflow-y-auto rounded-4 border border-outline-gray-2 bg-surface-base"
        :style="{ height: `${stageHeight}px` }"
      >
        <iframe
          :key="language"
          :src="source"
          :title="title"
          class="origin-top-left border-0"
          :class="resizing && 'pointer-events-none'"
          :style="{
            width: `${FRAME_WIDTH}px`,
            height: `${frameHeight}px`,
            transform: `scale(${scale})`,
          }"
          @load="measureFrame"
        />
      </div>
    </div>
  </div>
</template>
