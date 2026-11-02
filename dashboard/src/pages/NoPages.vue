<script setup>
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import EmptyState from '../components/EmptyState.vue'
</script>

<template>
  <AppPageHeader title="Commera" />

  <PageBody>
    <EmptyState
      icon="lucide-lock"
      title="No pages are available to you yet"
      description="Ask your store admin to give you access to an app."
    />
  </PageBody>
</template>
