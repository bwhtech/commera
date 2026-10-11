<script setup>
import PluginCardFrame from './PluginCardFrame.vue'

defineProps({
  entries: { type: Array, required: true },
  record: { type: Object, required: true },
  // `rail` is a section of a detail page's right rail; `stack` a bordered card in the main column.
  frame: { type: String, default: 'stack', validator: (value) => ['rail', 'stack'].includes(value) },
})

const emit = defineEmits(['reload'])

const FRAMES = {
  rail: 'border-t border-outline-gray-1 px-4 py-4',
  stack: 'rounded-5 border border-outline-gray-1 px-4 py-3.5',
}
</script>

<template>
  <PluginCardFrame
    v-for="entry in entries"
    :key="`${entry.key}:${record.revision}`"
    :entry="entry"
    :record="record"
    :frame-class="FRAMES[frame]"
    @reload="emit('reload')"
  />
</template>
