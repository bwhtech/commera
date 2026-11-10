<script setup>
import { computed, ref } from 'vue'
import { Button, FormControl, SettingsBody, SettingsRow, toast, useFileUpload } from 'frappe-ui'
import EmptyState from '../EmptyState.vue'
import SettingsPanelHeader from './SettingsPanelHeader.vue'
import { trySubmit, useAdminAction } from '../../data/api'
import { exportTranslationsUrl, translatableLanguages } from '../../data/translationExchange'
import { __ } from '../../data/translation'

const languages = translatableLanguages()
const languageOptions = languages.map(({ code, name }) => ({ label: name, value: code }))
const language = ref(languages[0]?.code ?? '')
const exportUrl = computed(() => exportTranslationsUrl(language.value))

const importAction = useAdminAction('translations.import_translations')
const { upload } = useFileUpload()
const fileInput = ref(null)
const isImporting = ref(false)
const report = ref(null)

async function importFile(event) {
  const file = event.target.files?.[0]
  // Cleared so that picking the same file again, after fixing it, fires `change` again.
  event.target.value = ''
  if (!file || isImporting.value) return
  report.value = null
  isImporting.value = true
  try {
    // Private: a merchant's working file, not a storefront asset.
    const uploaded = await upload(file, { private: true })
    const imported = await trySubmit(importAction, { file_url: uploaded.file_url, language: language.value })
    if (imported) report.value = importAction.data
  } catch {
    toast.error(__('Could not upload {0}', [file.name]))
  } finally {
    isImporting.value = false
  }
}
</script>

<template>
  <SettingsPanelHeader
    :title="__('Translations')"
    :description="__('Download a language as a CSV file, translate it, and upload it back.')"
  />

  <SettingsBody v-scroll-fade>
    <EmptyState
      v-if="!languages.length"
      compact
      icon="lucide-languages"
      :title="__('No language to translate into')"
      :description="__('Add a storefront language besides your default one first.')"
    />

    <template v-else>
      <div class="divide-y divide-outline-gray-1">
        <SettingsRow :title="__('Language')" :description="__('The language the file holds.')">
          <FormControl v-model="language" type="select" class="sm:w-40" :options="languageOptions" />
        </SettingsRow>
        <SettingsRow
          :title="__('Export')"
          :description="__('Every translatable field, with its default and translated content.')"
        >
          <Button :label="__('Export CSV')" icon-left="lucide-download" :href="exportUrl" />
        </SettingsRow>
        <SettingsRow
          :title="__('Import')"
          :description="__('Rows with empty translated content leave the translation as it is.')"
        >
          <input ref="fileInput" type="file" accept=".csv" class="hidden" @change="importFile" />
          <Button
            :label="__('Import CSV')"
            icon-left="lucide-upload"
            :loading="isImporting"
            @click="fileInput.click()"
          />
        </SettingsRow>
      </div>

      <section v-if="report" class="mt-4 rounded-5 border border-outline-gray-1 p-4">
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
            <!-- min-w-0 lets a long identification wrap instead of widening the panel. -->
            <span class="min-w-0 break-words text-ink-red-6">{{ error.message }}</span>
          </li>
        </ul>
      </section>
    </template>
  </SettingsBody>
</template>
