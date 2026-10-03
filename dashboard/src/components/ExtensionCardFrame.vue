<script setup>
import { computed, provide, ref } from 'vue'
import { CARD_CONTEXT } from '../extension-api/context'
import ExtensionHost from './ExtensionHost.vue'

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
</script>

<template>
  <section :hidden="!visible" :class="frameClass" :aria-label="entry.label">
    <h2 class="text-sm text-ink-gray-5">{{ entry.label }}</h2>
    <div class="mt-2 min-w-0">
      <ExtensionHost
        :entry="props.entry"
        :record="props.record"
        @ready="ready = true"
        @failed="failed = true"
        @reload="emit('reload')"
      />
    </div>
  </section>
</template>
