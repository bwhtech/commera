<script setup>
import { ref } from 'vue'
import IntegrationsPanel from './IntegrationsPanel.vue'

defineProps({
  store: { type: Object, required: true },
  title: { type: String, required: true },
  description: { type: String, required: true },
  // Opening the dialog should fetch; switching away and back should not.
  active: { type: Boolean, default: false },
})

const configuring = ref(null)
const sectionTakeover = ref(false)
</script>

<template>
  <!-- The list view scrolls as one pane: each section's SettingsBody sits in a block, so it grows
       to its content instead of splitting the height. An open editor fills the panel instead. -->
  <div
    v-scroll-fade
    class="flex min-h-0 flex-1 flex-col"
    :class="{ 'overflow-y-auto': !configuring && !sectionTakeover }"
  >
    <div
      v-if="!sectionTakeover"
      :class="configuring ? 'flex min-h-0 flex-1 flex-col' : 'shrink-0 [&_[data-slot=scroll-area-viewport]]:pb-0'"
    >
      <IntegrationsPanel
        v-model:configuring="configuring"
        :store="store"
        :active="active"
        :title="title"
        :description="description"
      />
    </div>

    <!-- A section that cannot open a screen of its own simply ignores `setTakeover`. -->
    <div v-if="!configuring" :class="sectionTakeover ? 'flex min-h-0 flex-1 flex-col' : 'shrink-0'">
      <slot :takeover="sectionTakeover" :set-takeover="(open) => (sectionTakeover = open)" />
    </div>
  </div>
</template>
