<script setup>
import { computed, onMounted, ref } from 'vue'
import { Badge, Button, Dropdown, LoadingText, Progress } from 'frappe-ui'
import AppPageHeader from '../../components/AppPageHeader.vue'
import PageBody from '../../components/PageBody.vue'
import EmptyState from '../../components/EmptyState.vue'
import TranslationImportDialog from '../../components/translations/TranslationImportDialog.vue'
import TranslationCounts from '../../components/translations/TranslationCounts.vue'
import { errorMessage } from '../../data/errors'
import { exportTranslationsUrl, translatableLanguages } from '../../data/translationExchange'
import { useTranslationOverview } from '../../data/translations'
import { groupResources, languageTotals } from '../../data/translationStatus'
import { onSettingsClose, openSettings } from '../../ia/settings'
import { __ } from '../../data/translation'

const { overview, overviewError, loadOverview } = useTranslationOverview()
const loading = ref(true)
onMounted(async () => {
  await loadOverview()
  loading.value = false
})
// "Add language" opens Settings over this page, which stays mounted behind it.
onSettingsClose(loadOverview)

const languages = computed(() => overview.value?.languages ?? [])
const resources = computed(() => groupResources(overview.value?.resources ?? []).flatMap((group) => group.resources))
const totals = computed(() =>
  Object.fromEntries(languages.value.map(({ code }) => [code, languageTotals(overview.value.counts[code])])),
)

const csvLanguages = computed(() => translatableLanguages())
const isImportOpen = ref(false)
const csvMenu = computed(() => [
  {
    group: __('Export'),
    options: csvLanguages.value.map((language) => ({
      label: __('Export {0}', [language.name]),
      icon: 'lucide-download',
      // A download answers with the file, so the page stays where it is.
      onClick: () => window.location.assign(exportTranslationsUrl(language.code)),
    })),
  },
  {
    group: __('Import'),
    hideLabel: true,
    options: [{ label: __('Import CSV'), icon: 'lucide-upload', onClick: () => (isImportOpen.value = true) }],
  },
])

function editorRoute(language, resource) {
  return { name: 'StorefrontTranslationEditor', params: { lang: language, resource } }
}
</script>

<template>
  <AppPageHeader :title="__('Translations')">
    <template #actions>
      <Dropdown v-if="csvLanguages.length" :options="csvMenu" align="end">
        <Button :label="__('CSV')" icon-left="lucide-file-spreadsheet" icon-right="lucide-chevron-down" />
      </Dropdown>
      <Button
        :label="__('Add language')"
        icon-left="lucide-plus"
        variant="solid"
        theme="gray"
        @click="openSettings('languages')"
      />
    </template>
  </AppPageHeader>

  <PageBody width="narrow">
    <LoadingText v-if="loading && !overview" />

    <EmptyState
      v-else-if="overviewError && !overview"
      icon="lucide-triangle-alert"
      :title="__('Could not load translations')"
      :description="errorMessage(overviewError)"
    />

    <EmptyState
      v-else-if="!languages.length"
      icon="lucide-languages"
      :title="__('Your storefront speaks {0} only', [overview.source.name])"
    >
      <Button variant="solid" theme="gray" icon-left="lucide-plus" :label="__('Add a language')" @click="openSettings('languages')" />
    </EmptyState>

    <div v-else class="space-y-8">
      <div
        class="grid divide-y divide-outline-gray-2 overflow-hidden rounded-5 border border-outline-gray-2 sm:grid-cols-3 sm:divide-y-0 sm:divide-x rtl:sm:divide-x-reverse"
      >
        <RouterLink
          v-for="language in languages"
          :key="language.code"
          :to="editorRoute(language.code, resources[0]?.type)"
          class="block p-4 hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none"
        >
          <div class="flex items-center gap-2">
            <p class="truncate text-base-semibold text-ink-gray-8">{{ language.name }}</p>
            <Badge v-if="!language.published" variant="subtle" theme="gray" :label="__('Hidden')" />
            <span class="ms-auto text-sm tabular-nums text-ink-gray-5">{{ totals[language.code].percent }}%</span>
          </div>
          <Progress class="mt-3" size="sm" :value="totals[language.code].percent" />
          <p class="mt-2 text-sm text-ink-gray-5">
            {{ __('{0} missing · {1} outdated', [totals[language.code].missing, totals[language.code].outdated]) }}
          </p>
        </RouterLink>
      </div>

      <section>
        <h2 class="text-lg-semibold text-ink-gray-8">{{ __('By resource') }}</h2>
        <div class="mt-3 overflow-x-auto">
          <!-- A table, not a grid: the language columns come from the store, and a grid would need
               its column template bound as an inline style. -->
          <table class="w-full min-w-[34rem] text-start">
            <thead>
              <tr class="border-b border-outline-gray-2 text-sm text-ink-gray-5">
                <th class="px-2 pb-2 text-start font-normal">{{ __('Resource') }}</th>
                <th v-for="language in languages" :key="language.code" class="px-2 pb-2 text-start font-normal">
                  {{ language.name }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="resource in resources" :key="resource.type" class="border-b border-outline-gray-1">
                <td class="px-2 py-2.5">
                  <span class="flex items-center gap-2 text-base text-ink-gray-8">
                    <span :class="[resource.icon, 'size-4 shrink-0 text-ink-gray-5']" aria-hidden="true" />
                    {{ resource.label }}
                  </span>
                </td>
                <td v-for="language in languages" :key="language.code" class="py-1.5">
                  <!-- Inline-flex keeps the hover on the counts, not on the whole column. -->
                  <RouterLink
                    :to="editorRoute(language.code, resource.type)"
                    class="inline-flex rounded-4 px-2 py-1 hover:bg-surface-gray-2 focus-visible:bg-surface-gray-2 focus-visible:outline-none"
                    :aria-label="__('{0} in {1}', [resource.label, language.name])"
                  >
                    <TranslationCounts :counts="overview.counts[language.code][resource.type]" />
                  </RouterLink>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </PageBody>

  <TranslationImportDialog v-model:open="isImportOpen" :languages="csvLanguages" @imported="loadOverview" />
</template>
