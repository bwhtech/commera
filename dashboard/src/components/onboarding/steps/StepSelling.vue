<script setup>
import { Switch } from 'frappe-ui'
import { draft } from '../../../ia/onboarding'
</script>

<template>
  <div class="space-y-4">
    <Switch v-model="draft.codEnabled" label="Cash on delivery" />
    <Switch v-model="draft.allowGuestCheckout" label="Guest checkout" />
  </div>
</template>
