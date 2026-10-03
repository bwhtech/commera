<script setup>
import { computed, ref } from 'vue'
import { ScrollArea } from 'frappe-ui'
import IntegrationsPanel from './IntegrationsPanel.vue'

const props = defineProps({
  store: { type: Object, required: true },
  title: { type: String, required: true },
  description: { type: String, required: true },
  // Opening the dialog should fetch; switching away and back should not.
  active: { type: Boolean, default: false },
  // The slot stacks several sections that together outgrow the dialog, so the column scrolls
  // as one; otherwise the slot's own body is the only thing that scrolls.
  scrollsAsOne: { type: Boolean, default: false },
})

const configuring = ref(null)
const sectionTakeover = ref(false)
const columnScrolls = computed(() => props.scrollsAsOne && !configuring.value && !sectionTakeover.value)
</script>

<template>
  <!-- Scrolling as one, each panel's own SettingsBody has no bounded height in here, so it
       grows to its content and the column scrolls from the carriers down to the last section.
       Otherwise reka's content div becomes a full-height flex column, so a takeover screen (or
       the slot's last panel) is bounded and scrolls its own body. The same element either way:
       swapping wrappers would remount the slot and drop which section is open. -->
  <ScrollArea
    v-scroll-fade
    class="min-h-0 flex-1"
    :viewport-class="columnScrolls ? '' : '[&>div]:flex [&>div]:h-full [&>div]:flex-col'"
  >
    <div
      v-if="!sectionTakeover"
      class="flex flex-col"
      :class="configuring ? 'min-h-0 flex-1' : 'shrink-0 [&_[data-slot=scroll-area-viewport]]:pb-0'"
    >
      <!-- Drops the 4rem of tail padding a whole panel ends on, through frappe-ui's own
           data-slot, so IntegrationsPanel itself stays generic. -->
      <IntegrationsPanel
        v-model:configuring="configuring"
        :store="store"
        :active="active"
        :title="title"
        :description="description"
      />
    </div>

    <!-- A section that cannot open a screen of its own simply ignores `setTakeover`. -->
    <slot v-if="!configuring" :takeover="sectionTakeover" :set-takeover="(open) => (sectionTakeover = open)" />
  </ScrollArea>
</template>
