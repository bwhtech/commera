<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { useEventListener } from '@vueuse/core'
import { Badge, Button, Dropdown, LoadingText, ScrollArea, toast } from 'frappe-ui'
import AppPageHeader from '../../components/AppPageHeader.vue'
import PageBody from '../../components/PageBody.vue'
import EmptyState from '../../components/EmptyState.vue'
import TranslationItemPicker from '../../components/translations/TranslationItemPicker.vue'
import TranslationRecord from '../../components/translations/TranslationRecord.vue'
import { getItems, saveTranslations, useTranslationOverview } from '../../data/translations'
import {
  fieldKey,
  groupResources,
  languageTotals,
  parseFieldKey,
  toDoCount,
} from '../../data/translationStatus'
import { changePending, savePending, useOpenedTranslation } from '../../data/translationEditorState'
import { useTranslationItems } from '../../data/translationItems'
import { onSettingsClose, openSettings } from '../../ia/settings'
import { confirmLeave } from '../../utils/confirmLeave'
import { useIsMobile } from '../../utils/useIsMobile'
import { errorMessage } from '../../data/errors'
import { __ } from '../../data/translation'

const route = useRoute()
const router = useRouter()
const isMobile = useIsMobile()

const languageCode = computed(() => route.params.lang)
const resourceType = computed(() => route.params.resource)

const { overview, loadOverview } = useTranslationOverview()
const overviewLoaded = ref(false)
onMounted(async () => {
  await loadOverview()
  overviewLoaded.value = true
})
// "Add a language" opens Settings over this page, which stays mounted behind it.
onSettingsClose(loadOverview)

const language = computed(() => overview.value?.languages.find((target) => target.code === languageCode.value))
const resourceGroups = computed(() => groupResources(overview.value?.resources ?? []))
const resource = computed(() =>
  resourceGroups.value.flatMap((group) => group.resources).find((described) => described.type === resourceType.value),
)

const filter = ref('todo')
const list = useTranslationItems(languageCode, resourceType, filter, getItems)
watch([languageCode, resourceType], () => (filter.value = 'todo'))

// A record opened from search or a link may sit outside the loaded list.
const { openedItem, unknownName, loadError: recordError, failedName, open } = useOpenedTranslation(languageCode, resourceType)
const selectedName = computed(() => route.query.record || (isMobile.value ? '' : list.items.value[0]?.name) || '')
const selectedItem = computed(
  () =>
    list.items.value.find((item) => item.name === selectedName.value) ??
    (openedItem.value?.name === selectedName.value ? openedItem.value : null),
)
watch(
  [languageCode, resourceType, selectedName, () => list.loading.value],
  async ([_language, _resource, name, loading]) => {
    if (!name || loading || selectedItem.value) return
    await open(name, list.fetchItem)
  },
  { immediate: true },
)

function select(name) {
  router.replace({ query: name ? { record: name } : {} })
}

function openResource(type, record) {
  if (type === resourceType.value && record) return select(record)
  router.push({
    name: 'StorefrontTranslationEditor',
    params: { lang: languageCode.value, resource: type },
    query: record ? { record } : {},
  })
}

// Unsaved values by field: a new translation, or an outdated one confirmed as still correct.
const pending = reactive({})
const dirtyCount = computed(() => Object.keys(pending).length)
const saving = ref(false)
const submitted = ref({})

function change(item, field, value) {
  const key = fieldKey(resourceType.value, item.name, field.field)
  changePending(pending, key, field, value, submitted.value)
}

function discard() {
  for (const key of Object.keys(pending)) delete pending[key]
}

async function save() {
  if (!dirtyCount.value || saving.value) return
  const translations = Object.entries(pending).map(([key, value]) => ({ ...parseFieldKey(key), value }))
  saving.value = true
  submitted.value = { ...pending }
  try {
    const saved = await savePending(pending, () => saveTranslations(languageCode.value, translations))
    if (saved === null) return
    const names = [...new Set(translations.map((translation) => translation.name))]
    const [fresh] = await Promise.all([list.refresh(names), loadOverview()])
    openedItem.value = fresh?.find((item) => item?.name === openedItem.value?.name) ?? openedItem.value
    toast.success(saved === 1 ? __('1 translation saved') : __('{0} translations saved', [saved]))
  } finally {
    submitted.value = {}
    saving.value = false
  }
}

async function leaveUnsaved() {
  const confirmed = await confirmLeave(
    __('Discard unsaved translations?'),
    dirtyCount.value === 1 ? __('1 change is not saved.') : __('{0} changes are not saved.', [dirtyCount.value]),
    __('Discard'),
  )
  if (confirmed) discard()
  return confirmed
}

onBeforeRouteLeave(() => (dirtyCount.value ? leaveUnsaved() : true))
// Another language or resource opens in this same component; picking a record only changes the query.
onBeforeRouteUpdate((to) => {
  const sameList = to.params.lang === languageCode.value && to.params.resource === resourceType.value
  return sameList || !dirtyCount.value ? true : leaveUnsaved()
})
useEventListener(window, 'beforeunload', (event) => {
  if (dirtyCount.value) event.preventDefault()
})

const languageMenu = computed(() => [
  {
    group: __('Translate into'),
    options: (overview.value?.languages ?? []).map((target) => ({
      label: __('{0} · {1} to do', [target.name, toDoCount(languageTotals(overview.value.counts[target.code]))]),
      onClick: () => router.push({ name: 'StorefrontTranslationEditor', params: { lang: target.code, resource: resourceType.value } }),
    })),
  },
  {
    group: __('More'),
    hideLabel: true,
    options: [{ label: __('Add a language'), icon: 'lucide-plus', onClick: () => openSettings('languages') }],
  },
])
</script>

<template>
  <AppPageHeader :title="__('Translations')">
    <template #title>
      <div class="flex min-w-0 items-center gap-1">
        <Button
          variant="ghost"
          icon="lucide-arrow-left"
          class="-ms-2 shrink-0 rtl:-scale-x-100"
          :label="__('Back to translations')"
          :route="{ name: 'StorefrontTranslations' }"
        />
        <RouterLink
          :to="{ name: 'StorefrontTranslations' }"
          class="rounded-4 px-1 text-lg text-ink-gray-5 hover:text-ink-gray-7 max-sm:hidden"
        >
          {{ __('Translations') }}
        </RouterLink>
        <span class="text-lg text-ink-gray-4 max-sm:hidden" aria-hidden="true">/</span>
        <Dropdown v-if="language" :options="languageMenu">
          <Button variant="ghost" icon-right="lucide-chevron-down" :aria-label="__('Language: {0}', [language.name])">
            <span class="truncate text-lg-semibold text-ink-gray-8">{{ language.name }}</span>
          </Button>
        </Dropdown>
        <Badge v-if="language && !language.published" variant="subtle" theme="gray" :label="__('Hidden')" />
      </div>
    </template>
    <template #actions>
      <span v-if="dirtyCount" class="text-sm text-ink-gray-5 max-sm:hidden">{{ __('{0} unsaved', [dirtyCount]) }}</span>
      <Button v-if="dirtyCount" :label="__('Discard')" :disabled="saving" @click="discard" />
      <Button :label="__('Save')" variant="solid" theme="gray" :disabled="!dirtyCount" :loading="saving" @click="save" />
    </template>
  </AppPageHeader>

  <PageBody v-if="!overviewLoaded && !overview"><LoadingText /></PageBody>

  <PageBody v-else-if="!language || !resource">
    <EmptyState icon="lucide-languages" :title="__('Nothing to translate here')">
      <Button :label="__('Back to translations')" :route="{ name: 'StorefrontTranslations' }" />
    </EmptyState>
  </PageBody>

  <!-- Two panes, each with its own scroll. A phone shows one at a time: the list until a record is picked. -->
  <div v-else class="flex min-h-0 flex-1 overflow-hidden">
    <TranslationItemPicker
      v-if="!isMobile || !selectedName"
      v-model:filter="filter"
      class="w-full shrink-0 border-outline-gray-2 sm:w-72 sm:border-e"
      :language="language"
      :resource="resource"
      :resource-groups="resourceGroups"
      :items="list.items.value"
      :total="list.total.value"
      :to-do-count="list.toDoCount.value"
      :selected-name="selectedName"
      :has-more="Boolean(list.nextCursor.value)"
      :loading="list.loading.value"
      :loaded="list.loaded.value"
      :load-error="list.loadError.value"
      @select="select"
      @open="openResource"
      @load-more="list.loadMore"
      @retry="list.load"
    />

    <!-- min-w-0: the shell's flex-1 child would otherwise hold the widest field's min-content width. -->
    <ScrollArea v-if="!isMobile || selectedName" v-scroll-fade class="min-w-0 flex-1">
      <PageBody width="narrow">
        <div v-if="!selectedItem && recordError && failedName === selectedName" role="alert">
          <p class="text-p-sm text-ink-red-6">{{ errorMessage(recordError, __('Could not load translations')) }}</p>
          <Button class="mt-2" :label="__('Retry')" @click="open(selectedName, list.fetchItem)" />
        </div>
        <LoadingText v-else-if="!selectedItem && (list.loading.value || (selectedName && selectedName !== unknownName))" />
        <TranslationRecord
          v-else-if="selectedItem"
          :item="selectedItem"
          :resource-name="resource.one"
          :language="language"
          :source-language="overview.source"
          :resource-type="resourceType"
          :pending="pending"
          :show-back="isMobile"
          @back="select('')"
          @change="change"
        />
      </PageBody>
    </ScrollArea>
  </div>
</template>
