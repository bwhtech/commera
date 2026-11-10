<script setup>
import { useRoute } from 'vue-router'
import { Button } from 'frappe-ui'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import EmptyState from '../components/EmptyState.vue'

const route = useRoute()
</script>

<template>
  <AppPageHeader :title="__('Page not found')" />

  <PageBody>
    <EmptyState
      icon="lucide-compass"
      :title="__('There is nothing at this address')"
      :description="__('{0} is not a screen in Commera.', [route.fullPath])"
    >
      <Button :label="__('Go to Overview')" variant="solid" theme="gray" route="/" />
    </EmptyState>
  </PageBody>
</template>
