<script setup>
import { toast } from 'frappe-ui'
import PluginHost from './PluginHost.vue'
import { runningSidebarAction } from '../ia/plugins'

// A sidebar action runs once per click: the host mounts it, its setup runs, and it is removed again.
function finish() {
  runningSidebarAction.value = null
}

function fail() {
  toast.error(`${runningSidebarAction.value?.label ?? 'This action'} couldn't run`)
  finish()
}
</script>

<template>
  <div v-if="runningSidebarAction" hidden>
    <PluginHost :key="runningSidebarAction.run" :entry="runningSidebarAction" @ready="finish" @failed="fail" />
  </div>
</template>
