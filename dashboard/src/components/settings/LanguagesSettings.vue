<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Alert, Button, FormControl, SettingsBody, SettingsRow, dialog, toast } from 'frappe-ui'
import AddLanguageDialog from './AddLanguageDialog.vue'
import EmptyState from '../EmptyState.vue'
import LanguageRow from './LanguageRow.vue'
import SettingsPanelHeader from './SettingsPanelHeader.vue'
import SettingsSkeleton from './SettingsSkeleton.vue'
import { languagePrefix, storefrontLanguageSettings as store } from '../../data/storefrontLanguages'
import { useTranslationOverview } from '../../data/translations'
import { languageTotals, toDoCount } from '../../data/translationStatus'
import { __ } from '../../data/translation'

const props = defineProps({
  active: { type: Boolean, default: false },
})

const { screen, loadError, loading: saving, languages, defaultLanguage, maxLanguages, isAtLimit, mutate } = store

const { overview, loadOverview } = useTranslationOverview()
const translationWork = computed(() =>
  Object.values(overview.value?.counts ?? {}).reduce((total, counts) => total + toDoCount(languageTotals(counts)), 0),
)
watch(() => props.active, (isActive) => {
  if (!isActive) return
  store.load()
  loadOverview()
}, { immediate: true })

const router = useRouter()
const hasTranslations = router.hasRoute('StorefrontTranslations')

const prefixOf = (code) => languagePrefix(code, defaultLanguage.value)
const languageOf = (code) => languages.value.find((language) => language.code === code)

const defaultOptions = computed(() =>
  languages.value
    .filter((language) => language.published)
    .map((language) => ({ label: language.name, value: language.code })),
)

// A native select shows what was picked even when the change is cancelled, so it is re-rendered
// from the stored default every time the admin picks one.
const defaultSelectKey = ref(0)

function askToMakeDefault(code) {
  defaultSelectKey.value += 1
  if (code === defaultLanguage.value) return
  const next = languageOf(code).name
  const current = languageOf(defaultLanguage.value)
  dialog.confirm({
    title: __('Make {0} the default language?', [next]),
    message: __('Your products and pages must already be written in {0}. {1} moves to {2}.', [
      next,
      current.name,
      languagePrefix(current.code, code),
    ]),
    confirmLabel: __('Make {0} the default', [next]),
    onConfirm: async () => {
      if (await mutate('set_default_storefront_language', { language: code })) {
        toast.success(__('{0} is the default language', [next]))
      }
    },
  })
}

async function setPublished(language, published) {
  if (!(await mutate('set_storefront_language_published', { language: language.code, published: published ? 1 : 0 }))) {
    return
  }
  toast.success(
    published
      ? __('{0} is live at {1}', [language.name, prefixOf(language.code)])
      : __('{0} is hidden from shoppers', [language.name]),
  )
}

// Admins can open a hidden language's storefront; shoppers get the default one there.
function preview(language) {
  window.open(prefixOf(language.code), '_blank', 'noopener')
}

function move(language, offset) {
  mutate('move_storefront_language', { language: language.code, offset })
}

function remove(language) {
  dialog.danger({
    title: __('Remove {0}?', [language.name]),
    message: __('{0} pages stop working. Its translations are kept.', [prefixOf(language.code)]),
    confirmLabel: __('Remove {0}', [language.name]),
    onConfirm: async () => {
      if (await mutate('remove_storefront_language', { language: language.code })) {
        toast.success(__('{0} removed', [language.name]))
      }
    },
  })
}

const isAdding = ref(false)

async function add({ code, publish }) {
  if (!(await mutate('add_storefront_language', { language: code, published: publish ? 1 : 0 }))) return
  isAdding.value = false
  const language = languageOf(code)
  toast.success(
    publish
      ? __('{0} is live at {1}', [language.name, prefixOf(code)])
      : __('{0} added. Shoppers cannot see it yet.', [language.name]),
  )
}

function openTranslations() {
  router.push({ name: 'StorefrontTranslations' })
}

function translate(language) {
  router.push({ name: 'StorefrontTranslationEditor', params: { lang: language.code, resource: 'product' } })
}
</script>

<template>
  <SettingsPanelHeader :title="__('Languages')" :description="__('Shoppers see published languages only.')">
    <template #actions>
      <Button
        variant="solid"
        theme="gray"
        icon-left="lucide-plus"
        :label="__('Add language')"
        :disabled="!screen || isAtLimit"
        @click="isAdding = true"
      />
    </template>
  </SettingsPanelHeader>

  <SettingsBody v-scroll-fade>
    <EmptyState
      v-if="loadError && !screen"
      compact
      icon="lucide-triangle-alert"
      :title="__('These could not be loaded')"
      :description="__('Your storefront still shows the languages it had.')"
    >
      <Button :label="__('Try again')" variant="subtle" theme="gray" @click="store.load()" />
    </EmptyState>

    <SettingsSkeleton v-else-if="!screen" :rows="4" />

    <template v-else>
      <div class="divide-y divide-outline-gray-1">
        <SettingsRow :title="__('Default language')" :description="__('The language your catalog is written in.')">
          <FormControl
            :key="defaultSelectKey"
            :model-value="defaultLanguage"
            type="select"
            class="sm:w-44"
            :options="defaultOptions"
            :disabled="saving"
            :aria-label="__('Default language')"
            @update:model-value="askToMakeDefault"
          />
        </SettingsRow>
      </div>

      <Alert
        v-if="isAtLimit"
        class="mt-4 !bg-surface-gray-2"
        theme="amber"
        :title="__('This storefront has {0} languages, the most it can have', [maxLanguages])"
        :description="__('Remove a language you no longer sell in to add another.')"
      />

      <div class="mt-6 flex items-baseline justify-between">
        <h3 class="text-base-semibold text-ink-gray-8">{{ __('Storefront languages') }}</h3>
        <span class="text-sm tabular-nums text-ink-gray-5">
          {{ __('{0} of {1}', [languages.length, maxLanguages]) }}
        </span>
      </div>
      <ul class="mt-2 divide-y divide-outline-gray-1 border-y border-outline-gray-1">
        <LanguageRow
          v-for="(language, index) in languages"
          :key="language.code"
          :language="language"
          :prefix="prefixOf(language.code)"
          :is-default="language.code === defaultLanguage"
          :is-first="index === 0"
          :is-last="index === languages.length - 1"
          :can-translate="hasTranslations"
          :busy="saving"
          @publish="setPublished(language, $event)"
          @preview="preview(language)"
          @move="move(language, $event)"
          @make-default="askToMakeDefault(language.code)"
          @translate="translate(language)"
          @remove="remove(language)"
        />
      </ul>

      <div v-if="hasTranslations" class="mt-6 divide-y divide-outline-gray-1 pb-6">
        <SettingsRow :title="__('Translations')" :description="__('{0} fields to translate or update', [translationWork])">
          <Button icon-right="lucide-arrow-right" :label="__('Open translations')" @click="openTranslations" />
        </SettingsRow>
      </div>
    </template>
  </SettingsBody>

  <AddLanguageDialog
    v-model:open="isAdding"
    :added="languages.map((language) => language.code)"
    :saving="saving"
    @add="add"
  />
</template>
