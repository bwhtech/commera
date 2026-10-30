<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useEventListener } from '@vueuse/core'
import { SECTION_GROUPS } from '../../data/themeLayout'

const props = defineProps({
  editor: { type: Object, required: true },
})

const { state, selectFromPreview } = props.editor

const FRAME_NAME = 'commera-theme-editor-preview'

const frame = ref(null)
const form = ref(null)
const csrfInput = ref(null)
const ready = ref(false)
let scrollY = 0

const action = computed(() => {
  const params = new URLSearchParams({ theme: state.theme, page: state.page, lang: state.language })
  return `/theme_editor_preview?${params}`
})

function post(type, data = {}) {
  if (!ready.value) return
  frame.value?.contentWindow?.postMessage({ type, ...data }, window.location.origin)
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
  ready.value = false
  form.value.action = action.value
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

useEventListener(window, 'message', (event) => {
  if (event.origin !== window.location.origin || event.source !== frame.value?.contentWindow) return
  const { type, ...data } = event.data || {}
  if (type === 'commera:scroll') scrollY = Number(data.y) || 0
  if (type === 'commera:select') selectFromPreview(data)
  if (type === 'commera:preview-ready') {
    ready.value = true
    post('commera:scroll-to', { y: scrollY })
    post('commera:highlight', { ...highlightTarget(), scroll: false })
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
      class="h-full overflow-hidden rounded-5 border border-outline-gray-2 bg-surface-base shadow-sm"
      :class="state.device === 'mobile' ? 'w-96' : 'w-full'"
    >
      <iframe
        ref="frame"
        :name="FRAME_NAME"
        title="Storefront preview"
        class="size-full"
        data-preview-frame
      />
    </div>
    <form ref="form" method="post" :target="FRAME_NAME" class="hidden">
      <input ref="csrfInput" type="hidden" name="csrf_token" />
    </form>
  </div>
</template>
