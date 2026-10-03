<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { appPage } from '../ia/extensions.js'
import ExtensionHost from '../components/ExtensionHost.vue'

const route = useRoute()
const entry = computed(() => appPage(route.params.app, route.params.page))
const path = computed(() => [].concat(route.params.path ?? []).join('/'))
</script>

<template>
  <div class="p-8">
    <ExtensionHost v-if="entry" :key="entry.url + path" :entry="entry" :path="path" />
    <p v-else class="text-ink-gray-6">No app page here.</p>
  </div>
</template>
