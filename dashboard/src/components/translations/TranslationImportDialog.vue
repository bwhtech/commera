<script setup>
import { ref, watch } from 'vue'
import { Button, Dialog, FormControl, toast, useFileUpload } from 'frappe-ui'
import { trySubmit, useAdminAction } from '../../data/api'
import { __ } from '../../data/translation'

const props = defineProps({
  // Target languages: { code, name }.
  languages: { type: Array, required: true },
})
const emit = defineEmits(['imported'])
const open = defineModel('open', { type: Boolean, default: false })

const language = ref('')
const importAction = useAdminAction('translations.import_translations')
const { upload } = useFileUpload()
const fileInput = ref(null)
const isImporting = ref(false)
const report = ref(null)

watch(() => props.languages, (available) => {
  if (!available.some(({ code }) => code === language.value)) {
    language.value = available[0]?.code ?? ''
  }
}, { immediate: true })

watch(open, (isOpen) => {
  if (!isOpen) return
  report.value = null
  language.value = props.languages[0]?.code ?? ''
})

async function importFile(event) {
  const file = event.target.files?.[0]
  // Cleared so that picking the same file again, after fixing it, fires `change` again.
  event.target.value = ''
  if (!file || !language.value || isImporting.value) return
  const targetLanguage = language.value
  report.value = null
  isImporting.value = true
  try {
    // Private: a merchant's working file, not a storefront asset.
    const uploaded = await upload(file, { private: true })
    const imported = await trySubmit(importAction, { file_url: uploaded.file_url, language: targetLanguage })
    if (imported) {
      report.value = importAction.data
      emit('imported')
    }
  } catch {
    toast.error(__('Could not upload {0}', [file.name]))
  } finally {
    isImporting.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open" :title="__('Import CSV')" size="md" :dismissible="!isImporting">
    <template #default>
      <div class="space-y-4">
        <FormControl
          v-if="languages.length > 1"
          v-model="language"
          type="select"
          :label="__('Language')"
          :disabled="isImporting"
          :options="languages.map(({ code, name }) => ({ label: name, value: code }))"
        />
        <input ref="fileInput" type="file" accept=".csv" class="hidden" @change="importFile" />
        <Button
          :label="__('Choose CSV file')"
          icon-left="lucide-upload"
          :loading="isImporting"
          :disabled="!language || isImporting"
          @click="fileInput.click()"
        />

        <section v-if="report" class="rounded-5 border border-outline-gray-1 p-4">
          <p class="text-base text-ink-gray-8">
            {{
              __('{0} updated, {1} unchanged, {2} skipped, {3} with errors', [
                report.updated,
                report.unchanged,
                report.skipped,
                report.errors.length,
              ])
            }}
          </p>
          <ul v-if="report.errors.length" class="mt-3 max-h-64 divide-y divide-outline-gray-1 overflow-y-auto">
            <li v-for="error in report.errors" :key="error.row" class="flex gap-3 py-2 text-p-sm">
              <span class="shrink-0 tabular-nums text-ink-gray-5">{{ __('Row {0}', [error.row]) }}</span>
              <!-- min-w-0 lets a long identification wrap instead of widening the dialog. -->
              <span class="min-w-0 break-words text-ink-red-6">{{ error.message }}</span>
            </li>
          </ul>
        </section>
      </div>
    </template>
  </Dialog>
</template>
