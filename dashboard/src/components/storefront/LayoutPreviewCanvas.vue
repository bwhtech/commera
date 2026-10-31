<script setup>
import { computed, ref } from 'vue'
import { onKeyStroke, useElementSize, useLocalStorage } from '@vueuse/core'
import { Button, TabButtons } from 'frappe-ui'
import LayoutPreviewFrame from './LayoutPreviewFrame.vue'

const props = defineProps({
  editor: { type: Object, required: true },
  maximised: { type: Boolean, default: false },
})

const emit = defineEmits(['toggle-maximise'])

const { state } = props.editor

const DESKTOP_WIDTH = 1280
const MOBILE_WIDTH = 390
const FRAME_GAP = 40
const PADDING = 24
const LABEL_HEIGHT = 28
const CONTROLS_HEIGHT = 64

const ZOOMS = [
  { label: 'Fit', value: 'fit' },
  { label: '75%', value: '0.75' },
  { label: '100%', value: '1' },
]

const canvas = ref(null)
const { width: canvasWidth, height: canvasHeight } = useElementSize(canvas)
const zooms = useLocalStorage('commera:theme-editor:zoom', {})

const zoom = computed({
  get: () => zooms.value[state.device] ?? 'fit',
  set: (value) => (zooms.value = { ...zooms.value, [state.device]: value }),
})

const layout = computed(() => {
  const availableWidth = Math.max(canvasWidth.value - PADDING * 2, 0)
  const availableHeight = Math.max(canvasHeight.value - PADDING - LABEL_HEIGHT - CONTROLS_HEIGHT, 0)
  const showDesktop = state.device !== 'mobile'
  const showMobile = state.device !== 'desktop'
  const gap = showDesktop && showMobile ? FRAME_GAP : 0
  const fixedWidth = (showDesktop ? DESKTOP_WIDTH : 0) + (showMobile ? MOBILE_WIDTH : 0)
  const scale = zoom.value === 'fit' ? Math.min(1, (availableWidth - gap) / fixedWidth) : Number(zoom.value)
  const desktopWidth = state.device === 'desktop' ? Math.max(DESKTOP_WIDTH, availableWidth / scale) : DESKTOP_WIDTH
  const height = availableHeight / scale
  const frames = []
  if (showDesktop) frames.push({ key: 'desktop', label: 'Desktop', width: Math.floor(desktopWidth), height })
  if (showMobile) frames.push({ key: 'mobile', label: 'Mobile', width: MOBILE_WIDTH, height })
  return { scale, frames }
})

onKeyStroke('Escape', (event) => {
  if (props.maximised && !event.target.closest?.('input, textarea, select, [contenteditable="true"]')) {
    emit('toggle-maximise')
  }
})
</script>

<template>
  <div class="relative size-full bg-surface-gray-2">
    <div
      ref="canvas"
      class="absolute inset-0 overflow-x-auto overflow-y-hidden"
      :data-preview-scale="layout.scale.toFixed(3)"
      data-preview-canvas
    >
      <div class="mx-auto flex w-fit gap-10 px-6 pt-6">
        <div v-for="frame in layout.frames" :key="frame.key" :data-preview-device="frame.key">
          <p class="h-7 text-p-sm text-ink-gray-5">{{ frame.label }} · {{ frame.width }}</p>
          <div
            class="overflow-hidden rounded-5 border border-outline-gray-2 bg-surface-base shadow-sm"
            :style="{ width: `${frame.width * layout.scale}px`, height: `${frame.height * layout.scale}px` }"
          >
            <div
              class="origin-top-left"
              :style="{ width: `${frame.width}px`, height: `${frame.height}px`, transform: `scale(${layout.scale})` }"
            >
              <LayoutPreviewFrame :editor="editor" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <div
      class="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-1 rounded-5 border border-outline-gray-2 bg-surface-base p-1 shadow-lg"
      data-zoom-controls
    >
      <TabButtons v-model="zoom" :options="ZOOMS" aria-label="Preview zoom" />
      <div class="mx-0.5 h-4 border-l border-outline-gray-2" />
      <Button
        variant="ghost"
        :icon="maximised ? 'lucide-minimize-2' : 'lucide-maximize-2'"
        :aria-label="maximised ? 'Restore panels' : 'Maximise preview'"
        :aria-pressed="maximised"
        @click="emit('toggle-maximise')"
      />
    </div>
  </div>
</template>
