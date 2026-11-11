<script setup>
import { ref, watch } from 'vue'
import MarketEditor from './MarketEditor.vue'
import MarketList from './MarketList.vue'
import { marketStore } from '../../../data/markets'
import { onSettingsClose } from '../../../ia/settings'

const props = defineProps({
  active: { type: Boolean, default: false },
})

// Local state, not a route: the panel lives inside the settings dialog, whose URL names only the tab.
const editing = ref(null)
onSettingsClose(() => {
  editing.value = null
})

// Re-read on each visit: Languages and General change what a market may pick.
watch(
  () => props.active,
  (isActive) => isActive && marketStore.load(),
  { immediate: true },
)
</script>

<template>
  <MarketEditor
    v-if="editing"
    :key="editing.handle === null ? 'create' : `market:${editing.handle}`"
    :handle="editing.handle"
    @back="editing = null"
    @created="(handle) => (editing = { handle })"
  />
  <MarketList v-else @open="(handle) => (editing = { handle })" />
</template>
