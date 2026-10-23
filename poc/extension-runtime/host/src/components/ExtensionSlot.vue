<script setup>
import { computed } from 'vue'
import { extensionsFor } from '../ia/extensions.js'
import ExtensionHost from './ExtensionHost.vue'

const props = defineProps({
  target: { type: String, required: true },
  resource: { type: Object, default: null },
})

const entries = computed(() => extensionsFor(props.target))
</script>

<template>
  <div v-if="entries.length" class="space-y-4" :data-extension-slot="target">
    <ExtensionHost
      v-for="entry in entries"
      :key="`${entry.app}:${entry.handle}`"
      :entry="entry"
      :resource="resource"
    />
  </div>
</template>
