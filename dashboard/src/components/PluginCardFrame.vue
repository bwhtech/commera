<script setup>
import { computed, onBeforeUnmount, provide, ref } from 'vue'
import { CARD_CONTEXT } from '../plugin-api/context'
import PluginHost from './PluginHost.vue'

const props = defineProps({
  entry: { type: Object, required: true },
  record: { type: Object, required: true },
  frameClass: { type: String, required: true },
})

const emit = defineEmits(['reload'])

const hidden = ref(false)
const ready = ref(false)
const failed = ref(false)

provide(CARD_CONTEXT, {
  hide: () => (hidden.value = true),
  show: () => (hidden.value = false),
  setHidden: (value) => (hidden.value = Boolean(value)),
})

// The frame waits for the card's first render, so a card that hides itself on load never shows an empty frame.
const visible = computed(() => failed.value || (ready.value && !hidden.value))

// A card whose module never finishes loading (a hung request, a plugin that never mounts) fires
// neither `ready` nor `failed`, and its frame stayed hidden for good. Past this it is shown as it is;
// a card that asked to be hidden stays hidden.
const READY_TIMEOUT_MS = 10000
const readyTimer = setTimeout(() => (ready.value = true), READY_TIMEOUT_MS)
onBeforeUnmount(() => clearTimeout(readyTimer))
</script>

<template>
  <section :hidden="!visible" :class="frameClass" :aria-label="entry.label">
    <h2 class="text-sm text-ink-gray-5">{{ entry.label }}</h2>
    <div class="mt-2 min-w-0">
      <PluginHost
        :entry="props.entry"
        :record="props.record"
        @ready="ready = true"
        @failed="failed = true"
        @reload="emit('reload')"
      />
    </div>
  </section>
</template>
