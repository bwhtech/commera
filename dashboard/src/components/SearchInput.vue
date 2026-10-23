<script setup>
import { TextInput } from 'frappe-ui'

const query = defineModel({ type: String, default: '' })
</script>

<template>
  <TextInput v-model="query">
    <template #prefix>
      <span class="lucide-search size-4" aria-hidden="true" />
    </template>
  </TextInput>
</template>
