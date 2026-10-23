<script setup>
import { computed } from 'vue'
import { Dialog } from 'frappe-ui'

const props = defineProps({ editor: { type: Object, required: true } })
const open = defineModel('open', { type: Boolean, default: false })
const { state } = props.editor

// What the site database would hold for this page: section order, block order
// and values. Theme files are not part of it and are never written.
const json = computed(() =>
  JSON.stringify({ theme: state.theme, template: state.template, sections: state.draft.templates[state.template] }, null, 2),
)
</script>

<template>
  <Dialog v-model:open="open" title="Layout data for this page" size="3xl">
    <p class="mb-3 text-base text-ink-gray-7">
      Saved in the site's database as <span class="font-medium">Theme Layout · {{ state.theme }} · {{ state.template }}</span>.
      The theme's own files never change, so updating the theme keeps these edits.
    </p>
    <pre class="max-h-[60vh] overflow-auto rounded bg-surface-gray-2 p-3 text-xs text-ink-gray-8">{{ json }}</pre>
  </Dialog>
</template>
