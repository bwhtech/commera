<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useEventListener } from '@vueuse/core'
import { SECTION_GROUPS } from '../../data/themeLayout'

const props = defineProps({
  editor: { type: Object, required: true },
})

const { state, selectFromPreview } = props.editor

const FRAME_NAMES = ['commera-theme-editor-preview-0', 'commera-theme-editor-preview-1']
const MAX_SCROLL_WAIT_FRAMES = 10

const frames = []
const form = ref(null)
const csrfInput = ref(null)
const visibleIndex = ref(null)
let latestRender = 0

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
  latestRender += 1
  const hiddenIndex = visibleIndex.value === 0 ? 1 : 0
  form.value.target = FRAME_NAMES[hiddenIndex]
  form.value.action = `${action.value}&render=${latestRender}`
  for (const input of form.value.querySelectorAll('input[data-part]')) input.remove()
  for (const part of state.parts) {
    const input = document.createElement('input')
    input.type = 'hidden'
    input.dataset.part = part.group
    input.name = SECTION_GROUPS.includes(part.group) ? `${part.group}_layout` : 'layout'
    input.value = JSON.stringify(part.layout)
    form.value.appendChild(input)
  }
  csrfInput.value.value = window.csrf_token ?? ''
  form.value.submit()
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
  if (renderNumber === latestRender) visibleIndex.value = index
}

useEventListener(window, 'message', (event) => {
  if (event.origin !== window.location.origin) return
  const index = frames.findIndex((frame) => frame?.contentWindow === event.source)
  if (index === -1) return
  const { type, ...data } = event.data || {}
  if (type === 'commera:select' && index === visibleIndex.value) selectFromPreview(data)
  if (type === 'commera:preview-ready' && index !== visibleIndex.value) {
    const renderNumber = Number(new URLSearchParams(event.source.location.search).get('render'))
    if (renderNumber === latestRender) swapIn(index, renderNumber)
  }
})

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
  <div class="flex h-full justify-center overflow-hidden bg-surface-gray-2 p-4">
    <div
      class="relative h-full overflow-hidden rounded-5 border border-outline-gray-2 bg-surface-base shadow-sm"
      :class="state.device === 'mobile' ? 'w-96' : 'w-full'"
    >
      <iframe
        v-for="(name, index) in FRAME_NAMES"
        :key="name"
        :ref="(element) => (frames[index] = element)"
        :name="name"
        title="Storefront preview"
        class="absolute inset-0 size-full"
        :class="{ 'pointer-events-none invisible': index !== visibleIndex }"
        :data-preview-frame="index === visibleIndex ? 'visible' : 'hidden'"
      />
    </div>
    <form ref="form" method="post" class="hidden">
      <input ref="csrfInput" type="hidden" name="csrf_token" />
    </form>
  </div>
</template>
