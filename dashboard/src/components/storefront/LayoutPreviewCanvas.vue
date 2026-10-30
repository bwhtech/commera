<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { onKeyStroke, useDebounceFn, useEventListener, useLocalStorage, useResizeObserver } from '@vueuse/core'
import Panzoom from '@panzoom/panzoom'
import { Button, Dropdown } from 'frappe-ui'
import LayoutPreviewFrame from './LayoutPreviewFrame.vue'

const props = defineProps({
  editor: { type: Object, required: true },
  maximised: { type: Boolean, default: false },
})

const emit = defineEmits(['toggle-maximise'])

const { state } = props.editor

const DESKTOP_WIDTH = 1280
const MOBILE_WIDTH = 390
const MOBILE_HEIGHT = 844
const MIN_DESKTOP_HEIGHT = 720
const FRAME_GAP = 80
const LABEL_HEIGHT = 24
const PADDING = 40
const CONTROLS_HEIGHT = 64

const canvas = ref(null)
const stage = ref(null)
const scale = ref(1)
const panning = ref(false)
const spaceHeld = ref(false)
const views = useLocalStorage('commera:theme-editor:canvas', {})
let panzoom = null
let canvasWidth = 0
let refitOnResize = false

const frames = computed(() => {
  const devices = []
  if (state.device !== 'mobile') {
    devices.push({
      key: 'desktop',
      label: 'Desktop',
      width: DESKTOP_WIDTH,
      height: views.value[state.device]?.height ?? MIN_DESKTOP_HEIGHT,
    })
  }
  if (state.device !== 'desktop') {
    devices.push({ key: 'mobile', label: 'Mobile', width: MOBILE_WIDTH, height: MOBILE_HEIGHT })
  }
  let left = 0
  return devices.map((device) => {
    const placed = { ...device, left }
    left += device.width + FRAME_GAP
    return placed
  })
})

const zoomOptions = computed(() => [
  { label: 'Zoom to fit', icon: 'lucide-scan', onClick: () => fit(true) },
  ...[0.5, 1, 2].map((value) => ({ label: `${value * 100}%`, onClick: () => zoomAroundCentre(value) })),
])

function fitView() {
  const availableWidth = canvas.value.clientWidth - PADDING * 2
  const availableHeight = canvas.value.clientHeight - PADDING - LABEL_HEIGHT - CONTROLS_HEIGHT
  if (state.device === 'mobile') {
    const fitScale = Math.min(1, availableHeight / MOBILE_HEIGHT, availableWidth / MOBILE_WIDTH)
    return centred(fitScale, MOBILE_WIDTH, null)
  }
  const contentWidth = state.device === 'both' ? DESKTOP_WIDTH + FRAME_GAP + MOBILE_WIDTH : DESKTOP_WIDTH
  const fitScale = Math.min(1, availableWidth / contentWidth)
  return centred(fitScale, contentWidth, Math.max(MIN_DESKTOP_HEIGHT, Math.round(availableHeight / fitScale)))
}

function centred(fitScale, contentWidth, height) {
  return {
    scale: fitScale,
    x: (canvas.value.clientWidth - contentWidth * fitScale) / 2 / fitScale,
    y: (PADDING + LABEL_HEIGHT) / fitScale,
    height,
  }
}

function applyView(view, animate = false) {
  views.value = { ...views.value, [state.device]: view }
  panzoom.zoom(view.scale, { animate, force: true })
  panzoom.pan(view.x, view.y, { animate, force: true })
}

function fit(animate = false) {
  applyView({ ...fitView(), fitted: true }, animate)
}

function leaveFit() {
  const view = views.value[state.device]
  if (view?.fitted) views.value = { ...views.value, [state.device]: { ...view, fitted: false } }
}

function zoomAroundCentre(value) {
  leaveFit()
  const bounds = canvas.value.getBoundingClientRect()
  panzoom.zoomToPoint(
    value,
    { clientX: bounds.left + bounds.width / 2, clientY: bounds.top + bounds.height / 2 },
    { animate: true },
  )
}

function zoomStep(direction) {
  leaveFit()
  if (direction > 0) panzoom?.zoomIn({ animate: true })
  else panzoom?.zoomOut({ animate: true })
}

const saveView = useDebounceFn((detail) => {
  const current = views.value[state.device] ?? {}
  views.value = { ...views.value, [state.device]: { ...current, scale: detail.scale, x: detail.x, y: detail.y } }
}, 200)

function mountPanzoom() {
  const view = views.value[state.device]?.scale ? views.value[state.device] : { ...fitView(), fitted: true }
  views.value = { ...views.value, [state.device]: view }
  panzoom = Panzoom(stage.value, {
    canvas: true,
    origin: '0 0',
    minScale: 0.1,
    maxScale: 4,
    step: 0.25,
    cursor: 'grab',
    startScale: view.scale,
    startX: view.x,
    startY: view.y,
  })
  scale.value = view.scale
}

useResizeObserver(canvas, () => {
  const width = canvas.value.clientWidth
  if (!width) return
  if (!panzoom) mountPanzoom()
  else if (refitOnResize || views.value[state.device]?.fitted) fit(refitOnResize)
  else if (width !== canvasWidth) {
    const pan = panzoom.getPan()
    panzoom.pan(pan.x + (width - canvasWidth) / 2 / panzoom.getScale(), pan.y, { force: true })
  }
  refitOnResize = false
  canvasWidth = width
})

useEventListener(stage, 'panzoomchange', (event) => {
  scale.value = event.detail.scale
  saveView(event.detail)
})
useEventListener(stage, 'panzoomstart', () => {
  panning.value = true
  leaveFit()
})
useEventListener(stage, 'panzoomend', () => (panning.value = false))

function zoomWithWheel(event) {
  leaveFit()
  panzoom.zoomWithWheel(event, { step: 0.2 })
}

useEventListener(
  canvas,
  'wheel',
  (event) => {
    if (!panzoom) return
    event.preventDefault()
    leaveFit()
    if (event.ctrlKey || event.metaKey) {
      zoomWithWheel(event)
      return
    }
    const pan = panzoom.getPan()
    const currentScale = panzoom.getScale()
    panzoom.pan(pan.x - event.deltaX / currentScale, pan.y - event.deltaY / currentScale)
  },
  { passive: false },
)

useEventListener(
  stage,
  'load',
  (event) => {
    const frame = event.target
    if (frame.tagName !== 'IFRAME' || !frame.contentWindow) return
    frame.contentWindow.addEventListener(
      'wheel',
      (wheelEvent) => {
        if (!wheelEvent.ctrlKey && !wheelEvent.metaKey) return
        wheelEvent.preventDefault()
        const bounds = frame.getBoundingClientRect()
        const ratio = bounds.width / frame.offsetWidth
        zoomWithWheel({
          deltaX: wheelEvent.deltaX,
          deltaY: wheelEvent.deltaY,
          clientX: bounds.left + wheelEvent.clientX * ratio,
          clientY: bounds.top + wheelEvent.clientY * ratio,
          preventDefault: () => {},
        })
      },
      { passive: false },
    )
  },
  true,
)

function isTyping(event) {
  return event.target.closest?.('input, textarea, select, [contenteditable="true"]')
}

onKeyStroke(' ', (event) => {
  if (isTyping(event)) return
  event.preventDefault()
  spaceHeld.value = true
})
onKeyStroke(' ', () => (spaceHeld.value = false), { eventName: 'keyup' })
onKeyStroke('Escape', (event) => {
  if (props.maximised && !isTyping(event)) emit('toggle-maximise')
})

watch(
  () => state.device,
  async () => {
    if (!panzoom) return
    await nextTick()
    if (views.value[state.device]?.scale && !views.value[state.device].fitted) applyView(views.value[state.device])
    else fit()
  },
)

watch(
  () => props.maximised,
  () => (refitOnResize = true),
)

onBeforeUnmount(() => panzoom?.destroy())
</script>

<template>
  <div ref="canvas" class="relative size-full overflow-hidden bg-surface-gray-2" data-preview-canvas>
    <div
      ref="stage"
      class="absolute left-0 top-0"
      :class="{ '[&_iframe]:pointer-events-none': panning || spaceHeld }"
      data-preview-stage
    >
      <div
        v-for="frame in frames"
        :key="frame.key"
        class="absolute top-0"
        :style="{ left: `${frame.left}px`, width: `${frame.width}px` }"
        :data-preview-device="frame.key"
      >
        <p
          class="absolute bottom-full left-0 mb-1 origin-bottom-left whitespace-nowrap text-p-sm text-ink-gray-5"
          :style="{ transform: `scale(${1 / scale})` }"
        >
          {{ frame.label }} · {{ frame.width }}
        </p>
        <div
          class="cursor-default overflow-hidden rounded-5 border border-outline-gray-2 bg-surface-base shadow-sm"
          :style="{ height: `${frame.height}px` }"
        >
          <LayoutPreviewFrame :editor="editor" />
        </div>
      </div>
    </div>

    <div
      class="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-0.5 rounded-5 border border-outline-gray-2 bg-surface-base p-1 shadow-lg"
      data-zoom-controls
    >
      <Button variant="ghost" icon="lucide-zoom-out" aria-label="Zoom out" @click="zoomStep(-1)" />
      <Dropdown :options="zoomOptions">
        <Button variant="ghost" class="min-w-16 tabular-nums" icon-right="lucide-chevron-down" data-zoom-level>
          {{ Math.round(scale * 100) }}%
        </Button>
      </Dropdown>
      <Button variant="ghost" icon="lucide-zoom-in" aria-label="Zoom in" @click="zoomStep(1)" />
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
