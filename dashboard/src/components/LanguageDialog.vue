<script setup>
import { computed, ref, watch } from 'vue'
import { Dialog, FormControl } from 'frappe-ui'
import { trySubmit } from '../data/api'
import { useLanguages, useSetLanguage } from '../data/language'
import { __ } from '../data/translation'
import { languagePickerOpen } from '../ia/languagePicker'

const languages = useLanguages()
const setLanguage = useSetLanguage()
const selected = ref(null)

watch(languagePickerOpen, async (isOpen) => {
  if (!isOpen) return
  await languages.fetch()
  selected.value = languages.data?.current ?? null
})

const hasChanged = computed(() => Boolean(selected.value) && selected.value !== languages.data?.current)

// A reload, not a re-render: every module-level label was translated as its module loaded.
async function apply() {
  if (!(await trySubmit(setLanguage, { language: selected.value }))) return
  window.location.reload()
}

const actions = computed(() => [
  {
    label: __('Switch language'),
    variant: 'solid',
    disabled: !hasChanged.value,
    loading: setLanguage.loading,
    onClick: apply,
  },
])
</script>

<template>
  <Dialog v-model:open="languagePickerOpen" :title="__('Language')" size="sm" :actions="actions">
    <FormControl
      v-model="selected"
      type="combobox"
      :label="__('Dashboard language')"
      :description="__('The dashboard reloads in the language you pick. Your storefront keeps its own languages.')"
      :options="languages.data?.options ?? []"
      :loading="languages.loading"
      :placeholder="__('Pick a language')"
    />
  </Dialog>
</template>
