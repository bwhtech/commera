<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { findPage } from '../ia/extensions'
import ExtensionPageFrame from '../components/ExtensionPageFrame.vue'
import NotFound from './NotFound.vue'

const route = useRoute()
const entry = computed(() => findPage(route.params.app, route.params.page))
const path = computed(() => [route.params.path ?? []].flat().join('/'))
</script>

<template>
  <NotFound v-if="!entry" />
  <!-- Keyed by the page, not the sub-path, so moving within an app updates `path` instead of remounting it,
       while moving to another page drops the header the last one set. -->
  <ExtensionPageFrame v-else :key="entry.key" :entry="entry" :path="path" :query="route.query" />
</template>
