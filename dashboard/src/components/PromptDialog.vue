<script setup>
/**
 * The app's one single-field question (asked through `askValue` in utils/confirmDialog.js): a
 * number or a pick from a list, for the menu actions that need one value. Built on FormDialog so
 * it is a sheet on a phone and asks before it drops a changed value, like every other form here.
 */
import { computed } from 'vue'
import { FormControl } from 'frappe-ui'
import FormDialog from './FormDialog.vue'
import { isPromptDirty, promptState, submitPrompt } from '../utils/confirmDialog'
import { __ } from '../data/translation'

const isEmpty = computed(() => String(promptState.value ?? '').trim() === '')
const isDirty = computed(isPromptDirty)
</script>

<template>
  <FormDialog
    v-model:open="promptState.open"
    size="md"
    :title="promptState.title"
    :description="promptState.message"
    :primary-label="promptState.confirmLabel"
    :primary-disabled="isEmpty"
    :reason="isEmpty ? (promptState.type === 'select' ? __('Pick one to continue.') : __('Enter a value to continue.')) : ''"
    :loading="promptState.loading"
    :dirty="isDirty"
    @submit="submitPrompt"
  >
    <FormControl
      v-model="promptState.value"
      :type="promptState.type"
      :options="promptState.type === 'select' ? promptState.options : undefined"
      :label="promptState.label"
      :inputmode="promptState.type === 'number' ? 'numeric' : undefined"
      required
      @keydown.enter.prevent="isEmpty || submitPrompt()"
    />
  </FormDialog>
</template>
