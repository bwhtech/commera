<script setup>
import { computed, defineComponent, onErrorCaptured, provide, ref, shallowRef, toRef } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'frappe-ui'
import { __, PLUGIN_CONTEXT } from '../plugin-api/context'
import EmptyState from './EmptyState.vue'
import { appLocation, settingsTabValue } from '../ia/plugins'
import { openSettings } from '../ia/settings'

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
  console.error(`[commera plugin ${props.entry.key}]`, error)
}

if (props.entry.error || !props.entry.module_url) fail(props.entry.error || 'This plugin has not been built yet.')

function navigate(to) {
  return router.push(appLocation(props.entry.app, to))
}

provide(PLUGIN_CONTEXT, {
  plugin: { app: props.entry.app, place: props.entry.place, name: props.entry.name, label: props.entry.label },
  path: toRef(props, 'path'),
  query: toRef(props, 'query'),
  record: toRef(props, 'record'),
  reload: () => emit('reload'),
  navigate,
  // No tab opens the plugin's own Settings tab; a Commera tab name such as 'payments' opens that one.
  openSettings: (tab) => openSettings(tab ?? settingsTabValue(props.entry.app)),
  toast,
  __,
})

const Plugin = shallowRef(null)

async function load() {
  try {
    const { app, place, name, module_url } = props.entry
    const url = import.meta.env.DEV ? `/@commera-plugin/${app}/${place}/${name}` : module_url
    const module = (await import(/* @vite-ignore */ url)).default
    Plugin.value = place === 'sidebar' ? runOnly(module) : module
  } catch (error) {
    fail(error)
  }
}

// A sidebar action has a <script setup> and no template: run its setup inside a component that draws nothing,
// so usePlugin() and the other composables still find this host's context.
function runOnly(module) {
  return defineComponent({
    name: 'PluginSidebarAction',
    setup(_props, context) {
      module.setup?.({}, context)
      return () => null
    },
  })
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
  <component :is="Plugin" v-else-if="Plugin" @vue:mounted="emit('ready')" />
</template>
