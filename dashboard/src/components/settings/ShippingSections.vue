<script setup>
import { ref } from 'vue'
import DeliveryOptionsPanel from './DeliveryOptionsPanel.vue'
import ShippingRatesPanel from './ShippingRatesPanel.vue'

defineProps({
  active: { type: Boolean, default: false },
})

// Whether any section below has taken over the tab; the carriers above hide on it.
const takeover = defineModel('configuring', { type: Boolean, default: false })
const openSection = ref(null)

function setSection(section, open) {
  openSection.value = open ? section : null
  takeover.value = open
}
</script>

<template>
  <!-- Sized like the carriers above it (IntegrationTabPanel): its own content height while
       stacked, so the rates below get the scroll area; the whole column once it takes over. -->
  <div
    v-if="!takeover || openSection === 'options'"
    class="flex flex-col"
    :class="takeover ? 'min-h-0 flex-1' : 'shrink-0 [&_[data-slot=scroll-area-viewport]]:pb-0'"
  >
    <DeliveryOptionsPanel
      :configuring="openSection === 'options'"
      :active="active"
      @update:configuring="setSection('options', $event)"
    />
  </div>

  <ShippingRatesPanel
    v-if="!takeover || openSection === 'rates'"
    :configuring="openSection === 'rates'"
    :active="active"
    @update:configuring="setSection('rates', $event)"
  />
</template>
