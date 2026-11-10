<script setup>
import { computed } from 'vue'
import { FormControl } from 'frappe-ui'
import { draft, flow } from '../../../ia/onboarding'
import { missingField } from '../../../ia/onboardingSteps'

const props = defineProps({
  needsPassword: { type: Boolean, default: false },
})

const missing = computed(() => (flow.showErrors ? missingField('you', draft, props) : ''))
</script>

<template>
  <div class="space-y-4">
    <FormControl
      v-model="draft.fullName"
      :label="__('Your name')"
      autocomplete="name"
      :error="missing === 'fullName' ? __('Required') : ''"
    />
    <FormControl
      v-if="needsPassword"
      v-model="draft.password"
      type="password"
      :label="__('Password')"
      autocomplete="new-password"
      :error="missing === 'password' ? __('Required') : ''"
    />
  </div>
</template>
