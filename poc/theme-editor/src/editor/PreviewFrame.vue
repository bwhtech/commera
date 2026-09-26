<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

// The live preview. The editor never touches the iframe's DOM: it posts the
// draft layout in and hears selections back, which is the same contract the
// real Jinja-rendered preview route would keep.
const props = defineProps({ editor: { type: Object, required: true } })
const { state, previewPayload, select } = props.editor

const frame = ref(null)
const ready = ref(false)

function post(scroll = false) {
  if (!ready.value) return
  frame.value?.contentWindow?.postMessage({ type: 'commera:render', data: previewPayload.value, scroll }, window.location.origin)
}

function onMessage(event) {
  if (event.origin !== window.location.origin || event.source !== frame.value?.contentWindow) return
  if (event.data?.type === 'commera:preview-ready') {
    ready.value = true
    post(true)
  }
  if (event.data?.type === 'commera:select') select(event.data.id, { scroll: false })
}

onMounted(() => window.addEventListener('message', onMessage))
onBeforeUnmount(() => window.removeEventListener('message', onMessage))

watch(previewPayload, () => post(false), { deep: true })
watch(() => state.scrollRequest, () => post(true))
</script>

<template>
  <div class="flex h-full justify-center overflow-hidden bg-surface-gray-2 p-4">
    <div
      class="h-full overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-white shadow-sm transition-all"
      :class="state.device === 'mobile' ? 'w-[390px]' : 'w-full'"
    >
      <iframe ref="frame" src="/preview.html" title="Storefront preview" class="h-full w-full" data-preview-frame />
    </div>
  </div>
</template>
