<script setup>
import { defineAsyncComponent, onErrorCaptured, provide, ref } from 'vue'
import { toast } from 'frappe-ui'
import { useRouter } from 'vue-router'
import { EXTENSION_CONTEXT } from '../extension-api/context.js'

// One extension, isolated: its own context, its own error boundary. A module
// that fails to load or throws while rendering becomes a small failure card;
// the rest of the page keeps working.
const props = defineProps({
  entry: { type: Object, required: true },
  resource: { type: Object, default: null },
  path: { type: String, default: '' },
})

const router = useRouter()
const failure = ref(null)

provide(EXTENSION_CONTEXT, {
  extension: { app: props.entry.app, handle: props.entry.handle, target: props.entry.target },
  resource: props.resource,
  path: props.path,
  toast,
  navigate: (to) =>
    router.push(to.startsWith('/') ? to : `/apps/${props.entry.app}/${props.entry.page}/${to}`),
  setTitle: (title) => (document.title = title),
})

const Extension = defineAsyncComponent({
  // @vite-ignore: the URL is data from the registry, resolved by the browser at runtime.
  loader: () => import(/* @vite-ignore */ props.entry.url).then((module) => module.default),
  onError: (error, _retry, fail) => {
    failure.value = error
    fail()
  },
})

onErrorCaptured((error) => {
  failure.value = error
  console.error(`[extension ${props.entry.app}:${props.entry.handle}]`, error)
  return false
})
</script>

<template>
  <div
    v-if="failure"
    class="rounded-5 border border-outline-red-2 bg-surface-red-1 px-4 py-3 text-sm text-ink-red-4"
    data-extension-failure
  >
    {{ entry.app }} · {{ entry.handle }} failed to load: {{ failure.message }}
  </div>
  <Extension v-else />
</template>
