<script>
export const plugin = { label: '$label' }
</script>

<script setup>
import { EmptyState } from '@commera/admin'
</script>

<template>
  <EmptyState title="$label" description="Build this page in commera/$folder/index.vue." />
</template>
