<script setup>
import { ref } from 'vue'
import DeliveryOptionsPanel from './DeliveryOptionsPanel.vue'
import ShippingRulesPanel from './ShippingRulesPanel.vue'

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
  <!-- Sized like the carriers above it (IntegrationTabPanel): no tail padding while stacked,
       the whole column once it takes over. -->
  <div
    v-if="!takeover || openSection === 'rules'"
    class="flex flex-col"
    :class="takeover ? 'min-h-0 flex-1' : '[&_[data-slot=scroll-area-viewport]]:pb-0'"
  >
    <ShippingRulesPanel
      :configuring="openSection === 'rules'"
      :active="active"
      @update:configuring="setSection('rules', $event)"
    />
  </div>

  <DeliveryOptionsPanel
    v-if="!takeover || openSection === 'options'"
    :configuring="openSection === 'options'"
    :active="active"
    @update:configuring="setSection('options', $event)"
  />
</template>
