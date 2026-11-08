<script setup>
import { Button } from 'frappe-ui'

defineProps({
  count: { type: Number, required: true },
  noun: { type: String, default: 'item' },
  // A bulk action is running: every action, and Done, waits for it rather than racing it.
  busy: { type: Boolean, default: false },
})

const emit = defineEmits(['done'])
</script>

<template>
  <!-- Selection is a mode, not a permanent state: while it is on, a row click
       picks rather than opens, so the bar has to say so and offer a way out. -->
  <div class="mt-3 flex flex-wrap items-center gap-2 rounded-4 border border-outline-gray-2 bg-surface-gray-1 px-3 py-2">
    <span class="text-base text-ink-gray-7">
      {{ count ? `${count} ${noun}${count > 1 ? 's' : ''} selected` : `Select ${noun}s to act on them` }}
    </span>
    <span v-if="!count" class="text-sm text-ink-gray-5">Rows pick instead of opening while this is on.</span>
    <div class="ml-auto flex flex-wrap gap-2">
      <!-- A fieldset so every action a screen slots in is inert with nothing selected, whatever it
           is: each handler already returns early on an empty selection, which read as a dead click. -->
      <fieldset :disabled="!count || busy" class="flex flex-wrap gap-2 disabled:opacity-50">
        <slot :count="count" />
      </fieldset>
      <Button label="Done" icon-left="lucide-check" :disabled="busy" @click="emit('done')" />
    </div>
  </div>
</template>
