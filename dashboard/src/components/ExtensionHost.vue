<script setup>
import { computed, onErrorCaptured, provide, ref, shallowRef, toRef } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'frappe-ui'
import { __, EXTENSION_CONTEXT } from '../extension-api/context'
import EmptyState from './EmptyState.vue'
import { appLocation } from '../ia/extensions'

const props = defineProps({
  entry: { type: Object, required: true },
  path: { type: String, default: '' },
  query: { type: Object, default: () => ({}) },
  // The record a card or an action sits on, as { doctype, name }.
  record: { type: Object, default: null },
  compact: { type: Boolean, default: true },
})

const emit = defineEmits(['reload', 'failed', 'ready'])

const router = useRouter()
const label = computed(() => props.entry.label || props.entry.app)
const failure = ref(null)

function fail(error) {
  failure.value = error?.message || String(error)
  emit('failed')
  console.error(`[commera app ${props.entry.key}]`, error)
}

if (props.entry.error || !props.entry.module_url) fail(props.entry.error || 'The app has not built this extension.')

function navigate(to) {
  return router.push(appLocation(props.entry.app, to))
}

provide(EXTENSION_CONTEXT, {
  extension: { app: props.entry.app, place: props.entry.place, name: props.entry.name, label: props.entry.label },
  path: toRef(props, 'path'),
  query: toRef(props, 'query'),
  record: toRef(props, 'record'),
  reload: () => emit('reload'),
  navigate,
  toast,
  __,
})

const Extension = shallowRef(null)

async function load() {
  try {
    Extension.value = (await import(/* @vite-ignore */ props.entry.module_url)).default
  } catch (error) {
    fail(error)
  }
}

if (!failure.value) load()

// A failed import, a render error or a throwing handler all land here; returning false keeps the rest of the dashboard alive.
onErrorCaptured((error) => {
  fail(error)
  return false
})
</script>

<template>
  <EmptyState
    v-if="failure"
    :compact="compact"
    icon="lucide-triangle-alert"
    :title="`${label} couldn't load`"
    :description="failure"
  />
  <component :is="Extension" v-else-if="Extension" @vue:mounted="emit('ready')" />
</template>
