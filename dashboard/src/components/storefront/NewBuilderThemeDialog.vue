<script setup>
import { ref, useId, watch } from 'vue'
import { Button, Dialog, ErrorMessage, FormControl } from 'frappe-ui'
import { useTheme } from '../../data/theme'
import { errorMessage } from '../../data/errors'
import { __ } from '../../data/translation'

const open = defineModel('open', { type: Boolean, required: true })

const { load, createBuilderTheme } = useTheme()

// The submit button sits outside the form, so `form` is what makes the browser run
// the name's `required` check.
const formId = useId()

const themeName = ref('')
const creating = ref(false)
const failure = ref('')

watch(open, (isOpen) => {
  if (!isOpen) return
  themeName.value = ''
  failure.value = ''
})

async function create() {
  creating.value = true
  failure.value = ''
  try {
    const { data, error } = await createBuilderTheme(themeName.value.trim())
    if (error) {
      failure.value = errorMessage(error)
      return
    }
    open.value = false
    // Opened before the reload is awaited: browsers only let a script open a tab
    // shortly after the click, and a slow reload would get it popup-blocked.
    window.open(data.editor_url, '_blank')
    await load()
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open" :title="__('New theme')" size="sm" :dismissible="!creating">
    <template #default>
      <form :id="formId" class="space-y-3" @submit.prevent="create">
        <FormControl v-model="themeName" :label="__('Theme name')" required :placeholder="__('Autumn drop')" />
        <p class="text-p-sm text-ink-gray-5">
          {{ __('It opens in Frappe Builder, where you can describe the design to the AI assistant.') }}
        </p>
        <ErrorMessage v-if="failure" :message="failure" />
      </form>
    </template>

    <template #actions>
      <Button
        class="w-full"
        type="submit"
        :form="formId"
        variant="solid"
        theme="gray"
        :label="__('Create theme')"
        :loading="creating"
      />
    </template>
  </Dialog>
</template>
