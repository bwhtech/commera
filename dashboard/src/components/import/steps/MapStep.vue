<script setup>
import { computed, ref } from 'vue'
import { Alert, Button, Select, Spinner } from 'frappe-ui'
import { useAdminRead } from '../../../data/api'
import {
  checkMapping,
  imp,
  isMappingChecked,
  setColumnField,
  setDefaultCollection,
} from '../../../data/importFlow'
import { TARGET_FIELDS, fieldLabel, isSameMapping, stillNeeded } from '../../../data/importMapping'
import { __ } from '../../../data/translation'
import ToneBadge from '../ToneBadge.vue'
import NewCollectionDialog from '../../NewCollectionDialog.vue'

const mapped = computed(() => Object.values(imp.mapping).filter(Boolean).length)

const hasCollectionColumn = computed(() => Object.values(imp.mapping).includes('collection'))
// The collection is listed apart from the columns, so the alert names only the columns still unmatched.
const missingColumns = computed(() =>
  stillNeeded(imp.mapping, imp.defaultCollection, isMappingChecked.value ? imp.missing : []).filter(
    (field) => field !== 'collection',
  ),
)

const collectionsRequest = useAdminRead('catalog.get_collections')
const collectionOptions = computed(() => [
  { label: __('Pick a collection'), value: '' },
  ...(collectionsRequest.data ?? []).map((name) => ({ label: name, value: name })),
])

// The same New collection dialog as Add product's, so a taken name is said under Name there too.
const newCollectionOpen = ref(false)

function addCollection() {
  newCollectionOpen.value = true
}

async function useNewCollection(name) {
  await collectionsRequest.reload()
  setDefaultCollection(name)
}

// A guess from a header that only contains a known name ("Variant Size"). The merchant's own pick is
// never second-guessed, so the badge goes as soon as they change that column.
const needsCheck = (header) =>
  imp.mapping[header] && imp.mapping[header] === imp.suggestedMapping[header] && imp.confidence[header] === 'low'

const hasOwnChanges = computed(() => !isSameMapping(imp.mapping, imp.suggestedMapping))
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-col items-start gap-3 sm:flex-row sm:gap-4">
      <div class="min-w-0 flex-1">
        <h2 class="text-lg-semibold text-ink-gray-9">{{ __('Match your columns') }}</h2>
        <p class="mt-1.5 text-p-base text-ink-gray-6">
          {{ __("We matched {0} of {1} columns for you. Columns set to “Don't import” are left out.", [mapped, imp.headers.length]) }}
        </p>
      </div>
      <Button
        v-if="hasOwnChanges"
        class="shrink-0"
        variant="subtle"
        icon-left="lucide-undo-2"
        :label="__('Use our suggestions')"
        :disabled="imp.phase === 'checking'"
        @click="checkMapping({ useSuggestions: true })"
      />
    </div>

    <Alert
      v-if="missingColumns.length"
      theme="red"
      :title="__('Still needed: {0}', [missingColumns.map(fieldLabel).join(', ')])"
      :description="__('Pick the column that holds it in the list next to that column.')"
    />
    <Alert
      v-else-if="imp.checkError && imp.phase !== 'checking'"
      theme="red"
      :title="imp.checkError"
      :primary-action="{ label: __('Try again'), onClick: () => checkMapping() }"
    />

    <div class="overflow-hidden rounded-5 border border-outline-gray-1">
      <div class="hidden grid-cols-2 gap-4 border-b border-outline-gray-1 bg-surface-gray-1 px-5 py-2.5 sm:grid">
        <span class="text-sm text-ink-gray-6">{{ __('Column in your file') }}</span>
        <span class="text-sm text-ink-gray-6">{{ __('Goes into') }}</span>
      </div>

      <div class="divide-y divide-outline-gray-1">
        <!-- Stacked below sm: the column and its sample above, the field below, so nothing scrolls sideways. -->
        <div
          v-for="header in imp.headers"
          :key="header"
          class="flex flex-col gap-2 px-4 py-3 sm:grid sm:grid-cols-2 sm:items-center sm:gap-4 sm:px-5"
        >
          <div class="min-w-0">
            <div class="truncate text-base text-ink-gray-8">{{ header }}</div>
            <div v-if="imp.samples[header]" class="truncate text-sm text-ink-gray-6">{{ imp.samples[header] }}</div>
          </div>
          <div class="flex min-w-0 items-center gap-2">
            <Select
              class="min-w-0 flex-1"
              :model-value="imp.mapping[header] ?? ''"
              :options="TARGET_FIELDS"
              :aria-label="__('Field for {0}', [header])"
              @update:model-value="(field) => setColumnField(header, field)"
            />
            <ToneBadge v-if="needsCheck(header)" class="shrink-0" :label="__('Check this')" />
          </div>
        </div>

        <!-- The collection every product goes into is one more "goes into" answer, so it is a row of
             the same grid: its picker then starts on the same line as every field picker above. -->
        <div
          v-if="!hasCollectionColumn"
          class="flex flex-col gap-2 px-4 py-3 sm:grid sm:grid-cols-2 sm:items-center sm:gap-4 sm:px-5"
        >
          <div class="min-w-0">
            <div class="text-base text-ink-gray-8">{{ __('No collection column') }}</div>
            <div class="text-p-sm text-ink-gray-6">{{ __('Every product goes into the one you pick. You can move them later.') }}</div>
          </div>
          <div class="flex min-w-0 items-center gap-2">
            <Select
              class="min-w-0 flex-1"
              :model-value="imp.defaultCollection"
              :options="collectionOptions"
              :aria-label="__('Collection for every product')"
              @update:model-value="setDefaultCollection"
            />
            <Button :label="__('New')" icon-left="lucide-plus" @click="addCollection" />
          </div>
        </div>
      </div>
    </div>

    <div v-if="imp.phase === 'checking'" class="flex items-center gap-2 text-sm text-ink-gray-6">
      <Spinner class="size-3.5" />
      {{ __('Checking your columns…') }}
    </div>

    <NewCollectionDialog v-model:open="newCollectionOpen" @created="useNewCollection" />
  </div>
</template>
