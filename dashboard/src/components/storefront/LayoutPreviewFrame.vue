<script setup>
import { computed, onMounted, ref, useId, watch } from 'vue'
import { useEventListener } from '@vueuse/core'
import { toast } from 'frappe-ui'
import { SECTION_GROUPS } from '../../data/themeLayout'

const props = defineProps({
  editor: { type: Object, required: true },
})

const emit = defineEmits(['scroll'])

const { state, selectFromPreview } = props.editor

const frameId = useId()
const FRAME_NAMES = [`commera-theme-editor-preview-${frameId}-0`, `commera-theme-editor-preview-${frameId}-1`]
const MAX_SCROLL_WAIT_FRAMES = 10
const RENDERING_DELAY_MS = 150

const frames = []
const form = ref(null)
const csrfInput = ref(null)
const visibleIndex = ref(null)
const rendering = ref(false)
let latestRender = 0
let readyRender = 0
let lastPosted = null
let renderingTimer = null

const action = computed(() => {
  const params = new URLSearchParams({ theme: state.theme, page: state.page, lang: state.language })
  return `/theme_editor_preview?${params}`
})

const visibleWindow = () => frames[visibleIndex.value]?.contentWindow

function post(type, data = {}, target = visibleWindow()) {
  target?.postMessage({ type, ...data }, window.location.origin)
}

function highlightTarget() {
  const selection = state.selection
  if (selection?.kind === 'section') {
    return { group: selection.group, id: selection.section, section: selection.section }
  }
  if (selection?.kind === 'block') return { group: selection.group, id: selection.block, section: selection.section }
  return { group: null, id: null, section: null }
}

function render() {
  if (!form.value || !state.loaded) return
  const layouts = state.parts.map((part) => [
    SECTION_GROUPS.includes(part.group) ? `${part.group}_layout` : 'layout',
    JSON.stringify(part.layout),
  ])
  const posted = JSON.stringify([action.value, state.settingsRevision, layouts])
  if (posted === lastPosted) return
  lastPosted = posted
  latestRender += 1
  const hiddenIndex = visibleIndex.value === 0 ? 1 : 0
  form.value.target = FRAME_NAMES[hiddenIndex]
  form.value.action = `${action.value}&render=${latestRender}`
  for (const input of form.value.querySelectorAll('input[data-part]')) input.remove()
  for (const [name, value] of layouts) {
    const input = document.createElement('input')
    input.type = 'hidden'
    input.dataset.part = name
    input.name = name
    input.value = value
    form.value.appendChild(input)
  }
  csrfInput.value.value = window.csrf_token ?? ''
  form.value.submit()
  clearTimeout(renderingTimer)
  renderingTimer = setTimeout(() => (rendering.value = true), RENDERING_DELAY_MS)
}

const renderNumberOf = (index) => Number(new URLSearchParams(frames[index].contentWindow.location.search).get('render'))

function onFrameLoad(index) {
  if (index === visibleIndex.value || renderNumberOf(index) !== latestRender || readyRender === latestRender) return
  clearTimeout(renderingTimer)
  rendering.value = false
  lastPosted = null
  toast.error('The preview could not be updated. Your changes are kept.', { id: 'theme-preview-failed' })
}

const nextFrame = () => new Promise((resolve) => requestAnimationFrame(resolve))

async function swapIn(index, renderNumber) {
  const target = frames[index].contentWindow
  if (target.document.readyState !== 'complete') {
    await new Promise((resolve) => target.addEventListener('load', resolve, { once: true }))
  }
  if (renderNumber !== latestRender) return
  const scrollY = visibleWindow()?.scrollY ?? 0
  post('commera:scroll-to', { y: scrollY }, target)
  post('commera:highlight', { ...highlightTarget(), scroll: false }, target)
  for (let count = 0; count < MAX_SCROLL_WAIT_FRAMES && Math.abs(target.scrollY - scrollY) > 1; count += 1) {
    await nextFrame()
  }
  if (renderNumber !== latestRender) return
  visibleIndex.value = index
  clearTimeout(renderingTimer)
  rendering.value = false
}

useEventListener(window, 'message', (event) => {
  if (event.origin !== window.location.origin) return
  const index = frames.findIndex((frame) => frame?.contentWindow === event.source)
  if (index === -1) return
  const { type, ...data } = event.data || {}
  if (type === 'commera:select' && index === visibleIndex.value) selectFromPreview(data)
  if (type === 'commera:scroll' && index === visibleIndex.value) emit('scroll', data)
  if (type === 'commera:preview-ready' && index !== visibleIndex.value) {
    const renderNumber = renderNumberOf(index)
    readyRender = renderNumber
    if (renderNumber === latestRender) swapIn(index, renderNumber)
  }
})

defineExpose({ scrollToSection: (position) => post('commera:scroll-to-section', position) })

onMounted(render)
watch(() => [state.previewToken, state.language], render)
watch(
  () => state.scrollRequest,
  () => post('commera:highlight', { ...highlightTarget(), scroll: true }),
)
watch(
  () => state.selection,
  () => post('commera:highlight', { ...highlightTarget(), scroll: false }),
  { deep: true },
)
</script>

<template>
  <div class="relative size-full">
    <iframe
      v-for="(name, index) in FRAME_NAMES"
      :key="name"
      :ref="(element) => (frames[index] = element)"
      :name="name"
      title="Storefront preview"
      class="absolute inset-0 size-full"
      :class="{ 'pointer-events-none invisible': index !== visibleIndex }"
      :data-preview-frame="index === visibleIndex ? 'visible' : 'hidden'"
      @load="onFrameLoad(index)"
    />
    <div
      v-if="rendering"
      data-preview-rendering
      class="absolute inset-0 bg-black-overlay-100 backdrop-blur-[1px]"
      role="progressbar"
      aria-label="Updating preview"
    >
      <div class="h-0.5 overflow-hidden bg-surface-gray-3">
        <div class="preview-progress h-full w-1/3 bg-surface-gray-7" />
      </div>
    </div>
    <form ref="form" method="post" class="hidden">
      <input ref="csrfInput" type="hidden" name="csrf_token" />
    </form>
  </div>
</template>

<style scoped>
.preview-progress {
  animation: preview-progress 1s ease-in-out infinite;
}

@keyframes preview-progress {
  from {
    transform: translateX(-100%);
  }
  to {
    transform: translateX(300%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .preview-progress {
    animation: none;
    width: 100%;
  }
}
</style>
