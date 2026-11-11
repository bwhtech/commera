<script setup>
import { ref } from 'vue'
import { TabButtons } from 'frappe-ui'
import { __ } from '../../data/translation'
import AppPageHeader from '../../components/AppPageHeader.vue'
import PageBody from '../../components/PageBody.vue'
import NavigationEditor from '../../components/storefront/NavigationEditor.vue'
import FooterEditor from '../../components/storefront/FooterEditor.vue'

const MENUS = [
  { label: __('Main navigation'), value: 'main' },
  { label: __('Footer'), value: 'footer' },
]

const menuId = ref('main')
</script>

<template>
  <AppPageHeader :title="__('Navigation')" />

  <PageBody>
    <TabButtons v-model="menuId" size="sm" :options="MENUS" />

    <div class="mt-4">
      <!-- Both editors stay mounted: each owns an iframe preview and a loaded tree,
           and remounting on every tab switch would refetch and collapse them. -->
      <NavigationEditor v-show="menuId === 'main'" />
      <FooterEditor v-show="menuId === 'footer'" />
    </div>
  </PageBody>
</template>
